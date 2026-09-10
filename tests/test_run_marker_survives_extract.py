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
"""A run has to be able to say it is running for the whole of a long run.

Gloss reported IDLE for a fourteen hour run that was translating throughout.
The marker was written when the extract stage began and refreshed by each
translated chunk, so between those two events nothing beat it -- and reading
the corpus takes longer than the ten minutes after which Gloss treats a quiet
marker as the remains of a dead run and deletes it.

Deleting it was terminal: a beat refused to rebuild a marker that was not
already there, on the grounds that a beat is not a reason to invent a run. So
the first translated chunk could not undo the damage, nor could any of the
four hundred and fifty seven after it.

Both halves are tested here, because either one alone still leaves a window
where a live run reports as idle.
"""
import importlib.machinery
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"

# What ProcessBtWrapper.STALE_AFTER_MILLIS is set to. A marker quiet for
# longer than this is deleted.
STALE_AFTER_MILLIS = 10 * 60 * 1000


def load(name):
    """These are commands, not modules: no .py suffix to import by."""
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(
            name.replace("-", "_"), str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def home_with(tmp_path, made=0, done=0, age_seconds=0, catalogued=None):
    """A BIGTRANSLATE_HOME with chunks extracted and translated.

    `done` is what this machine translated into its own flat directory.
    `catalogued` is what the archive holds, which on a distributed run is
    every node's output and so a superset.
    """
    strings = tmp_path / "data" / "strings"
    translated = tmp_path / "data" / "translated"
    strings.mkdir(parents=True, exist_ok=True)
    translated.mkdir(parents=True, exist_ok=True)
    when = time.time() - age_seconds
    for n in range(made):
        f = strings / ("chunk-%05d.json" % n)
        f.write_text("[]", encoding="utf-8")
        os.utime(f, (when, when))
    for n in range(done):
        f = translated / ("chunk-%05d.json" % n)
        f.write_text("{}", encoding="utf-8")
        os.utime(f, (when, when))
    if catalogued:
        catalog = tmp_path / "data" / "translated-catalog"
        catalog.mkdir(parents=True, exist_ok=True)
        for n in range(catalogued):
            # The versioner nests each product under a directory of its own
            # name, so a catalogued chunk is a directory.
            holder = catalog / ("chunk-%05d.json" % n)
            holder.mkdir(exist_ok=True)
            (holder / ("chunk-%05d.json" % n)).write_text(
                "{}", encoding="utf-8")
            os.utime(holder, (when, when))
    return tmp_path


def marker(tmp_path):
    return json.loads((tmp_path / "data" / "run").read_text(encoding="utf-8"))


class TestABeatCanRebuildAMarkerThatWasDeleted:

    def test_a_beat_with_no_marker_records_the_run(self, tmp_path, monkeypatch):
        home = home_with(tmp_path, made=458, done=106)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")

        assert not (home / "data" / "run").exists()
        assert run_marker.main(["beat"]) == 0
        assert (home / "data" / "run").exists(), (
            "a translate task beating is a stage saying it is working; "
            "refusing to record that leaves a live run reporting as idle "
            "for the rest of its hours")

        recorded = marker(home)
        assert recorded["status"] == "TRANSLATING"
        assert recorded["chunksTotal"] == 458
        assert recorded["chunksDone"] == 106

    def test_a_rebuilt_marker_is_dated_from_the_work_not_from_now(
            self, tmp_path, monkeypatch):
        # The failure this prevents is a plausible one, which is what makes
        # it dangerous: 106 chunks divided by no elapsed time is a rate of
        # thousands per minute and an estimate of "about 1m remaining".
        home = home_with(tmp_path, made=458, done=106, age_seconds=7200)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        run_marker.main(["beat"])

        recorded = marker(home)
        now = int(time.time() * 1000)
        two_hours = 2 * 60 * 60 * 1000
        assert now - recorded["startedAt"] > two_hours - 60000, (
            "a run whose oldest chunk is two hours old did not start now")
        assert now - recorded["translatingSince"] > two_hours - 60000, (
            "the rate is chunks since translating began; dating that to now "
            "makes every estimate wrong in the direction of good news")

    def test_a_beat_still_refreshes_a_marker_that_is_there(
            self, tmp_path, monkeypatch):
        home = home_with(tmp_path, made=458, done=1)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        run_marker.main(["start", "--path", "/corpus"])
        first = marker(home)

        time.sleep(0.01)
        run_marker.main(["beat"])
        second = marker(home)

        assert second["heartbeatAt"] > first["heartbeatAt"]
        assert second["startedAt"] == first["startedAt"], (
            "a refresh must not restart the clock")
        assert second["path"] == "/corpus", "a beat keeps what start recorded"
        assert "rebuiltAt" not in second

    def test_clear_still_clears(self, tmp_path, monkeypatch):
        home = home_with(tmp_path, made=10, done=10)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        run_marker.main(["start"])
        assert (home / "data" / "run").exists()
        run_marker.main(["clear"])
        assert not (home / "data" / "run").exists(), (
            "the join clears the marker; a run that ended must not keep "
            "reporting itself")


class TestExtractBeatsWhileItReads:

    def test_the_read_loop_beats(self, tmp_path):
        # No chunk exists until the read is finished, so this is the only
        # evidence the stage is alive -- and the stretch it covers is longer
        # than the bound after which the marker is thrown away.
        extract = load("bt-extract-strings")
        beats = []
        paths = []
        for n in range(6):
            f = tmp_path / ("part-%d.tsv" % n)
            f.write_bytes(b"value\n")
            paths.append(f.as_posix())

        extract.distinct_strings(paths, {0}, progress_every=2,
                                 beat=lambda: beats.append(1))
        assert len(beats) == 3, (
            "the corpus read is the longest stretch of a run in which "
            "nothing is written where a watcher can see it")

    def test_the_read_still_works_without_a_beat(self, tmp_path):
        extract = load("bt-extract-strings")
        f = tmp_path / "part.tsv"
        f.write_bytes(b"hola\nadios\nhola\n")
        seen, cells, rows, nbytes, elapsed = extract.distinct_strings(
            [f.as_posix()], {0})
        assert seen == {b"hola", b"adios"}

    def test_a_failing_beat_does_not_sink_the_stage(self, tmp_path):
        # Saying how far along we are is never worth losing the read for.
        extract = load("bt-extract-strings")

        def explode():
            raise RuntimeError("no marker for you")

        f = tmp_path / "part.tsv"
        f.write_bytes(b"hola\n")
        try:
            extract.distinct_strings([f.as_posix()], {0}, progress_every=1,
                                     beat=explode)
        except RuntimeError:
            raise AssertionError(
                "a stage that read the corpus successfully must not fail "
                "because it could not update a status file")


class TestTheGapThatWasLeftOpen:

    def test_extract_beats_often_enough_to_outlast_the_stale_bound(self):
        # The two halves have to meet: beating every 200 files is only a fix
        # if 200 files take less than the bound to read. On the measured run
        # the whole read was ~10 minutes for ~1,900 files, so 200 files is
        # roughly a minute.
        source = (BIN / "bt-extract-strings").read_text(encoding="utf-8")
        assert "progress_every=200" in source
        assert "beat()" in source, (
            "the beat has to be on the progress tick, not once at the start")


class TestProgressCountsEveryNodesWork:
    """The manager's flat directory is its own share, not the run's total.

    Each node writes a translated chunk into its own flat directory and the
    File Manager brings it back to the archive, so the archive is the only
    complete copy. Counting the flat directory alone reported 43 of 458 on a
    two node run that had done 121 -- the same mistake #79 fixed for the
    join, left standing here.
    """

    def test_the_archive_is_counted(self, tmp_path, monkeypatch):
        home = home_with(tmp_path, made=458, done=43, catalogued=121)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")

        seen = run_marker.progress(home.as_posix())
        assert seen["chunksDone"] == 121, (
            "43 of 458 understates the rate by nearly threefold and makes "
            "the estimate of when the run ends useless")
        assert seen["stage"] == "translating"

    def test_a_single_machine_run_still_counts(self, tmp_path, monkeypatch):
        # No archive at all, which is every single machine install.
        home = home_with(tmp_path, made=10, done=4)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        assert run_marker.progress(home.as_posix())["chunksDone"] == 4

    def test_a_chunk_in_both_places_is_one_chunk(self, tmp_path, monkeypatch):
        # The manager translates as well as coordinates, so its own chunks
        # are in the flat directory and, once ingested, the archive too.
        home = home_with(tmp_path, made=10, done=4, catalogued=4)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        assert run_marker.progress(home.as_posix())["chunksDone"] == 4, (
            "adding the two would report more chunks done than exist")

    def test_the_stage_turns_over_when_every_chunk_is_done(
            self, tmp_path, monkeypatch):
        # Counting the flat directory alone, done never reached made on a
        # distributed run, so the stage never left translating.
        home = home_with(tmp_path, made=458, done=43, catalogued=458)
        monkeypatch.setenv("BIGTRANSLATE_HOME", home.as_posix())
        run_marker = load("bt-run-marker")
        assert run_marker.progress(home.as_posix())["stage"] == "joining"
