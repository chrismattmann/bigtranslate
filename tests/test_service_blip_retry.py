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
"""A translation service that is not ready yet is not a chunk that cannot be done.

ServiceUnavailable is the one failure here that is recoverable by definition:
the service is loading its model, or was restarted underneath us, and the same
request will work shortly. On the last run eight chunks were lost to exactly
that, permanently, because a failed task was the end of it.

Nothing else is retried. A malformed chunk fails the same way every time, and
retrying it would burn a node rather than a chunk. The workflow retries the
whole task as a backstop for everything this cannot identify; this is the
cheaper recovery for the case the task itself understands.
"""
import importlib.machinery
import importlib.util
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"


def load(name):
    """These are commands, not modules: no .py suffix to import by."""
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(name.replace("-", "_"),
                                             str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTranslator:
    """Stands in for the shim, failing on demand."""

    class ServiceUnavailable(Exception):
        pass

    def __init__(self, fail_times=0, fail_forever=False, other_error=None):
        self.fail_times = fail_times
        self.fail_forever = fail_forever
        self.other_error = other_error
        self.calls = 0

    def translate_batch(self, service_url, batch, beam_size, max_length,
                        timeout):
        self.calls += 1
        if self.other_error is not None:
            raise self.other_error
        if self.fail_forever or self.calls <= self.fail_times:
            raise self.ServiceUnavailable(
                "the translation service at %s stopped answering partway "
                "through ([Errno 61] Connection refused)" % service_url)
        return ["en-" + s for s in batch]


@pytest.fixture
def chunker():
    return load("bt-translate-chunk")


def translate(chunker, translator, strings, retries=3, batch_size=2):
    return chunker.translate_chunk(
        translator, strings, "http://127.0.0.1:8766", batch_size,
        1, 128, 30, retries, 0, "chunk-00001.json")


class TestItWaitsOutAServiceThatIsNotReady:

    def test_a_blip_is_survived(self, chunker):
        translator = FakeTranslator(fail_times=2)
        out = translate(chunker, translator, ["hola", "adios"])

        assert out == {"hola": "en-hola", "adios": "en-adios"}
        assert translator.calls == 3, "two refusals then the real answer"

    def test_it_gives_up_rather_than_retrying_forever(self, chunker):
        # A service that never comes back is a chunk that cannot be done now,
        # and the workflow decides whether to try the whole task again.
        translator = FakeTranslator(fail_forever=True)
        with pytest.raises(FakeTranslator.ServiceUnavailable):
            translate(chunker, translator, ["hola"], retries=2)

        assert translator.calls == 3, "the first attempt plus two retries"

    def test_only_the_known_transient_failure_is_retried(self, chunker):
        # A malformed chunk fails identically every time. Retrying it would
        # cost a node three times over and still fail.
        translator = FakeTranslator(other_error=ValueError("not JSON"))
        with pytest.raises(ValueError):
            translate(chunker, translator, ["hola"])

        assert translator.calls == 1, "a permanent failure is not retried"

    def test_a_healthy_service_is_not_slowed_down(self, chunker):
        translator = FakeTranslator()
        out = translate(chunker, translator, ["hola", "adios", "gracias"])

        assert len(out) == 3
        assert translator.calls == 2, "two batches of two, no extra calls"


class TestWorkAlreadyDoneIsKept:

    def test_a_blip_does_not_discard_the_batches_already_translated(self,
                                                                   chunker):
        """The reason this retries per batch rather than per chunk.

        A chunk is a hundred and fifty batches. Losing the hundred already
        translated because the hundred and first arrived during a restart is
        most of the cost of the failure.
        """
        strings = ["s%d" % n for n in range(10)]

        class FailsOnTheThirdBatch(FakeTranslator):
            def translate_batch(self, service_url, batch, beam_size,
                                max_length, timeout):
                self.calls += 1
                if self.calls == 3:
                    raise self.ServiceUnavailable("restarting")
                return ["en-" + s for s in batch]

        translator = FailsOnTheThirdBatch()
        out = translate(chunker, translator, strings)

        assert len(out) == 10, "every string still arrives"
        assert out["s0"] == "en-s0"
        assert out["s9"] == "en-s9"
        # 5 batches of two, plus the one refusal that was retried.
        assert translator.calls == 6
