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
"""The translate stage beats the marker on a timer, not on every batch.

Gloss deletes a marker whose heartbeat is older than ten minutes, so a
chunk that spends minutes inside one model request has to say it is still
there. Beating per batch does that and a great deal more: a batch is 32
strings, a chunk is 5,000, and a 458 chunk run comes to about 71,500
beats -- each one a Python interpreter that re-reads the marker, walks two
directories and rewrites the file, measured at 23ms.
"""

import importlib.machinery
import importlib.util
import sys
import types

import pytest

from conftest import BIN


def load():
    """Load bt-translate-chunk without importing Pantogloss."""
    for name in ("pantogloss", "numpy"):
        sys.modules.setdefault(name, types.ModuleType(name))
    loader = importlib.machinery.SourceFileLoader(
        "bt_translate_chunk", str(BIN / "bt-translate-chunk"))
    spec = importlib.util.spec_from_loader("bt_translate_chunk", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


chunk = load()


@pytest.fixture
def spy(monkeypatch):
    """Count the subprocess calls a beat would make."""
    calls = []
    monkeypatch.setattr(chunk.subprocess, "run",
                        lambda *a, **k: calls.append(a))
    monkeypatch.setattr(chunk, "_last_beat", 0.0)
    return calls


class TestItBeatsOnATimer:

    def test_the_first_beat_goes_through(self, spy, monkeypatch):
        monkeypatch.setattr(chunk.time, "time", lambda: 1000.0)
        chunk.beat_run_marker()
        assert len(spy) == 1

    def test_a_second_beat_a_moment_later_is_dropped(self, spy, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(chunk.time, "time", lambda: now[0])
        chunk.beat_run_marker()
        for _ in range(200):
            now[0] += 0.1
            chunk.beat_run_marker()
        assert len(spy) == 1, "beat once a minute, not once a batch"

    def test_it_beats_again_once_the_interval_has_passed(self, spy, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(chunk.time, "time", lambda: now[0])
        chunk.beat_run_marker()
        now[0] += chunk.BEAT_EVERY_SECONDS + 1
        chunk.beat_run_marker()
        assert len(spy) == 2

    def test_the_interval_keeps_a_margin_on_the_stale_bound(self):
        # Gloss deletes a marker after ten minutes. Beating at that
        # interval would race it; the margin is what makes it safe.
        assert chunk.BEAT_EVERY_SECONDS <= 60, (
            "a beat this rare risks the ten minute stale bound")

    def test_force_beats_regardless(self, spy, monkeypatch):
        monkeypatch.setattr(chunk.time, "time", lambda: 1000.0)
        chunk.beat_run_marker()
        chunk.beat_run_marker(force=True)
        assert len(spy) == 2


class TestABeatIsNeverWorthTheChunk:

    def test_a_failing_marker_does_not_raise(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no such file")
        monkeypatch.setattr(chunk.subprocess, "run", boom)
        monkeypatch.setattr(chunk, "_last_beat", 0.0)
        chunk.beat_run_marker()   # must not propagate
