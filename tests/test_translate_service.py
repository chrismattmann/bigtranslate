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
