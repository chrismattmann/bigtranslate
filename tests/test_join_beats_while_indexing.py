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
"""Indexing is the longest silent stretch of a run.

Solr holds the documents uncommitted until the end, so the index reads as empty
the whole way through and nothing else the join writes is visible to a watcher.
Gloss deletes a marker whose heartbeat has gone quiet and calls the run dead, so
ten minutes into a join it reported IDLE while four shards were busy.

#83 fixed exactly this for the extract pass and left the join out, four lines
away in the same file.
"""
import importlib.machinery
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
JOIN = BIN / "bt-join-index"

# ProcessBtWrapper.STALE_AFTER_MILLIS
STALE_AFTER_SECONDS = 10 * 60


def load(name):
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(
            name.replace("-", "_"), str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheBeatIsOnTheBatchPath:
    """Where it sits is the whole point: at the start only is what broke."""

    def test_the_beat_happens_per_batch_not_once(self):
        source = JOIN.read_text(encoding="utf-8")
        loop = source[source.index("for path in mine:"):]
        assert "beat()" in loop, (
            "a beat outside the indexing loop fires once and the marker goes "
            "stale for the rest of the run")

    def test_it_is_guarded_at_the_call_site(self):
        source = JOIN.read_text(encoding="utf-8")
        loop = source[source.index("for path in mine:"):]
        call = loop[loop.index("beat()") - 200:loop.index("beat()") + 200]
        assert "try:" in call and "except" in call, (
            "a join that indexed successfully must not fail because a status "
            "file could not be written")

    def test_a_batch_is_a_frequent_enough_event(self):
        # 5000 documents a batch against a ten minute staleness bound: the
        # two halves have to meet, or beating changes nothing.
        source = JOIN.read_text(encoding="utf-8")
        assert '"--batch-size", type=int, default=5000' in source


class TestTheBeaterItself:

    def test_it_invokes_the_run_marker(self, tmp_path, monkeypatch):
        # A real beat through the real script: the marker must appear.
        home = tmp_path
        (home / "data" / "strings").mkdir(parents=True)
        (home / "data" / "translated").mkdir(parents=True)
        for n in range(3):
            (home / "data" / "strings" / ("chunk-%05d.json" % n)).write_text(
                "[]", encoding="utf-8")
            (home / "data" / "translated" / ("chunk-%05d.json" % n)).write_text(
                "{}", encoding="utf-8")
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())

        joiner = load("bt-join-index")
        joiner.run_marker_beat()

        marker = home / "data" / "run"
        assert marker.exists(), (
            "the beat has to reach bt-run-marker, or the join is silent")
        recorded = json.loads(marker.read_text(encoding="utf-8"))
        assert recorded["stage"] == "joining", (
            "every chunk is translated by the time the join runs")
        assert time.time() * 1000 - recorded["heartbeatAt"] < 60000

    def test_it_survives_a_missing_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BIGTRANSLATE_HOME", raising=False)
        joiner = load("bt-join-index")
        joiner.run_marker_beat()  # must not raise

    def test_it_survives_an_unrunnable_marker(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BIGTRANSLATE_HOME", tmp_path.as_posix())
        joiner = load("bt-join-index")
        original = joiner.subprocess.run

        def explode(*a, **k):
            raise OSError("no interpreter for you")

        joiner.subprocess.run = explode
        try:
            joiner.run_marker_beat()  # must not raise
        finally:
            joiner.subprocess.run = original


class TestTheJoinStillClearsWhenItIsDone:

    def test_the_pge_clears_the_marker_after_indexing(self):
        pge = (ROOT / "pge" / "src" / "main" / "resources" / "policy"
               / "no_filter" / "PgeConfig_JoinIndex.xml").read_text(
                   encoding="utf-8")
        clear = pge.index("bt-run-marker clear")
        index = pge.rindex("bt-join-index")
        assert clear > index, (
            "clearing before the indexing finishes would report the run over "
            "while it is still going")
