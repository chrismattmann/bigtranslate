# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Translation goes through the service, and says so when it cannot.

The PGE ran once per split and loaded the model each time -- about thirty
seconds, forty-nine times over a ten-file baseline, loading the same model
again every time. It now asks a running "pantogloss serve" instead.

There is deliberately no fallback to loading the model in-process. A fallback
would be invisible: the run would take the time it always did and nobody would
learn the service was never reached. So the interesting cases here are the
failures, and that each one says something different and useful.
"""
import http.server
import json
import threading
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PGE = REPO / "distribution" / "src" / "main" / "resources" / "bin" / "pantogloss-translatejson"


def _load():
    spec = importlib.util.spec_from_loader(
        "translatejson", loader=None, origin=str(PGE))
    module = importlib.util.module_from_spec(spec)
    exec(compile(PGE.read_text(), str(PGE), "exec"), module.__dict__)
    return module


tj = _load()


class _Handler(http.server.BaseHTTPRequestHandler):
    health = {"status": "ok", "model_status": "ready", "ready": True}
    translation = None

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, type(self).health)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        asked = json.loads(self.rfile.read(length))
        texts = asked["text"]
        if type(self).translation is not None:
            self._send(200, {"translation": type(self).translation})
            return
        self._send(200, {"translation": ["EN:" + t for t in texts],
                         "count": len(texts)})


class _NotPantogloss(http.server.BaseHTTPRequestHandler):
    """What a plain `python3 -m http.server` does: a cheerful 404."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


@pytest.fixture
def server():
    made = []

    def start(handler):
        httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        made.append(httpd)
        return "http://127.0.0.1:%d" % httpd.server_address[1]

    yield start
    for httpd in made:
        httpd.shutdown()


def test_a_ready_service_is_accepted(server):
    url = server(_Handler)
    health = tj.check_service(url, timeout=5)
    assert health["ready"] is True


def test_nothing_listening_says_how_to_start_one():
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.check_service("http://127.0.0.1:9", timeout=2)
    said = str(raised.value)
    assert "no translation service" in said
    assert "pantogloss serve" in said, "does not say how to fix it"


def test_something_else_on_the_port_is_not_reported_as_unreachable(server):
    """The failure that actually happened.

    Pantogloss's default port is an ordinary one, and a plain
    `python3 -m http.server` was sitting on it. That is a successful HTTP
    response, not a connection failure, and calling it "unreachable" sends
    the reader looking for the wrong thing entirely.
    """
    url = server(_NotPantogloss)
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.check_service(url, timeout=5)
    said = str(raised.value)
    assert "not Pantogloss" in said, said
    assert "what is on that port" in said, said


def test_a_service_still_loading_says_to_wait(server):
    class Loading(_Handler):
        health = {"status": "ok", "model_status": "loading", "ready": False}

    url = server(Loading)
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.check_service(url, timeout=5)
    said = str(raised.value)
    assert "not ready" in said
    assert "loading" in said


def test_a_batch_comes_back_in_the_order_it_was_sent(server):
    url = server(_Handler)
    out = tj.translate_batch(url, ["uno", "dos", "tres"], 1, 50, 10)
    assert out == ["EN:uno", "EN:dos", "EN:tres"]


def test_a_short_answer_is_refused_rather_than_misaligned(server):
    """Zipping a short reply against the batch would silently mislabel every
    translation after the gap, which is worse than failing."""
    class Short(_Handler):
        translation = ["only one"]

    url = server(Short)
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.translate_batch(url, ["uno", "dos", "tres"], 1, 50, 10)
    assert "refusing to guess" in str(raised.value)


def test_the_model_is_not_loaded_in_this_process():
    """The whole point: no in-process load, and no quiet fallback to one."""
    source = PGE.read_text()
    assert "Translator.from_pretrained" not in source, (
        "the PGE still loads the model itself")
    assert "DEFAULT_SERVICE_URL" in source


def test_setup_requires_a_pantogloss_new_enough_to_be_safe():
    """0.19.0 serialises concurrent callers into the model itself.

    Earlier servers ran them straight into a shared Keras model and Metal
    execution context, and MPSGraph aborted the process on the mismatched
    shapes; 0.18.0 avoided that by allowing only one at a time. The version
    is checked after installing rather than asked for in the specifier
    because PANTOGLOSS_SOURCE may be a working checkout, whose reported
    version is whatever its pyproject says.
    """
    setup = (REPO / "distribution" / "src" / "main" / "resources"
             / "bin" / "bigtranslate-setup").read_text()
    assert "PANTOGLOSS_REQUIRED" in setup, "no version floor is declared"
    assert "0.19.0" in setup, "the floor is not 0.19.0"
    assert "importlib.metadata" in setup, (
        "the installed version is never read, so the floor is not enforced")
    assert "TOO OLD" in setup, "an older Pantogloss is installed silently"


def test_the_floor_can_be_overridden():
    setup = (REPO / "distribution" / "src" / "main" / "resources"
             / "bin" / "bigtranslate-setup").read_text()
    assert "${PANTOGLOSS_REQUIRED:-0.19.0}" in setup


def test_pantogloss_is_installed_from_pypi_by_default():
    """It is published now, so setup no longer needs a checkout to point at."""
    setup = (REPO / "distribution" / "src" / "main" / "resources"
             / "bin" / "bigtranslate-setup").read_text()
    assert "PANTOGLOSS_SOURCE=${PANTOGLOSS_SOURCE:-pantogloss}" in setup, (
        "without a source the setup installs no Pantogloss at all")


def test_the_metal_single_slot_clamp_is_gated_on_the_version():
    """The clamp belongs to the old server, not to Apple silicon.

    0.19 admits callers concurrently and funnels them through one TensorFlow
    worker, so pinning Metal to a single slot there reintroduces exactly the
    queue the single slot caused: on the ten-file corpus it left 26,921
    summed queue seconds against 3,973 of inference.
    """
    oodt = (REPO / "distribution" / "src" / "main" / "resources"
            / "bin" / "oodt").read_text()
    assert "pantogloss_batches_dynamically" in oodt, (
        "nothing asks whether the server can batch for us")
    assert "! pantogloss_batches_dynamically" in oodt, (
        "the single-slot clamp is not gated on the version")


def test_dynamic_batching_flags_are_only_sent_to_servers_that_have_them():
    """An older server treats them as unknown arguments and refuses to start."""
    oodt = (REPO / "distribution" / "src" / "main" / "resources"
            / "bin" / "oodt").read_text()
    assert "--dynamic-batch-wait-ms" in oodt, "the collection window is never set"
    assert "--max-coalesced-batch-size" in oodt
    body = oodt[oodt.index("batching=\"\""):oodt.index("--dynamic-batch-wait-ms")]
    assert "pantogloss_batches_dynamically" in body, (
        "the flags are sent unconditionally")


def test_the_batching_window_is_configurable():
    env = (REPO / "distribution" / "src" / "main" / "resources"
           / "bin" / "setenv.sh").read_text()
    for name in ("PANTOGLOSS_BATCH_WAIT_MS", "PANTOGLOSS_COALESCED_BATCH",
                 "PANTOGLOSS_COALESCED_CHARS"):
        assert "export %s=${%s:-" % (name, name) in env, (
            "%s cannot be overridden" % name)


class _Busy(_Handler):
    """Answers 503 queue_timeout a few times, then succeeds.

    This is what a single inference slot does when eight workers submit into
    it: the service is healthy and the request is fine, it simply waited
    longer than the server allows.
    """

    refusals = 2
    seen = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        asked = json.loads(self.rfile.read(length))
        type(self).seen += 1
        if type(self).seen <= type(self).refusals:
            self._send(503, {"detail": {"code": "queue_timeout",
                                        "message": "translation queue wait timed out"}})
            return
        self._send(200, {"translation": ["EN:" + t for t in asked["text"]]})


def test_a_busy_queue_is_waited_out_not_treated_as_a_failure(server, monkeypatch):
    """Losing a split to a queue timeout cost 42 batches on one run, which
    finished with 1,546 of 43,851 postings and no other sign of trouble."""
    monkeypatch.setattr(tj, "QUEUE_TIMEOUT_BACKOFF", 0)
    _Busy.seen = 0
    url = server(_Busy)

    out = tj.translate_batch(url, ["uno", "dos"], 1, 50, 10)

    assert out == ["EN:uno", "EN:dos"], "the batch was lost to a busy queue"
    assert _Busy.seen == 3, "it did not retry twice before succeeding"


def test_a_queue_that_never_clears_eventually_gives_up(server, monkeypatch):
    """Retrying is for a queue that drains; a service wedged for good should
    still say so rather than hanging on it."""
    monkeypatch.setattr(tj, "QUEUE_TIMEOUT_BACKOFF", 0)

    class Always(_Busy):
        refusals = 10 ** 6
        seen = 0

    url = server(Always)
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.translate_batch(url, ["uno"], 1, 50, 10)
    assert "queue full" in str(raised.value)


def test_other_refusals_are_still_fatal(server):
    """Only a queue timeout is worth retrying. A service that is absent, or
    not Pantogloss, or has no model, will be the same on the next attempt."""
    class Broken(_Handler):
        def do_POST(self):
            self._send(413, {"detail": {"code": "batch_too_large"}})

    url = server(Broken)
    with pytest.raises(tj.ServiceUnavailable) as raised:
        tj.translate_batch(url, ["uno"], 1, 50, 10)
    said = str(raised.value)
    assert "refused" in said and "413" in said


def test_the_service_is_given_a_queue_wait_that_suits_one_slot():
    """Thirty seconds is the service's own default and assumes a slot per
    caller. With one slot and eight workers, waiting is the normal path."""
    oodt = (REPO / "distribution" / "src" / "main" / "resources"
            / "bin" / "oodt").read_text()
    assert "--queue-timeout" in oodt, "the service keeps its 30s default"
    assert "pantogloss_queue_timeout" in oodt
