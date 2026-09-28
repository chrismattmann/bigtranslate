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
"""Two different callers issue "start", and only one of them knows the run.

bin/bigtranslate starts a run knowing the corpus path and the moment it began.
The extract stage's PgeConfig also issues a start, and knows neither: its
--path is "[CorpusDir]", which on the 2026-09-27 run substituted to nothing.

A start that discarded the existing marker therefore reset startedAt from
13:13:50 to 13:24:52 -- eleven minutes into the run it was supposedly
beginning -- and wrote an empty path over the corpus path. Gloss spent the rest
of that run showing no path and the wrong elapsed time, and every rate derived
from startedAt was wrong by the length of the extract.

A start that finds a live marker is a stage of a run already under way. A
genuinely new run follows a clear, which removes the marker, so there is
nothing to carry forward and the distinction needs no flag.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = (ROOT / "distribution" / "src" / "main" / "resources" / "bin"
          / "bt-run-marker")


def run(home, *args):
    env = dict(os.environ)
    env["BIGTRANSLATE_HOME"] = str(home)
    return subprocess.run([sys.executable, str(MARKER), *args],
                          capture_output=True, text=True, env=env)


def marker(home):
    return json.loads((home / "data" / "run").read_text())


def fresh(tmp_path):
    home = tmp_path / "home"
    (home / "data").mkdir(parents=True)
    return home


CORPUS = "/Volumes/CHIPOTLE_BRICK/data/xdata/employmentdata/employment"


def test_a_stage_start_keeps_the_corpus_path(tmp_path):
    home = fresh(tmp_path)
    assert run(home, "start", "--path", CORPUS, "--started-by", "cli").returncode == 0
    # The extract stage, whose [CorpusDir] substituted to nothing.
    assert run(home, "start", "--path", "", "--started-by", "workflow").returncode == 0
    assert marker(home)["path"] == CORPUS, (
        "the stage's empty --path erased the corpus path, so Gloss shows a "
        "run against nothing")


def test_a_stage_start_keeps_the_real_start_time(tmp_path):
    home = fresh(tmp_path)
    run(home, "start", "--path", CORPUS, "--started-by", "cli")
    began = marker(home)["startedAt"]
    run(home, "start", "--path", "", "--started-by", "workflow")
    assert marker(home)["startedAt"] == began, (
        "the stage's start reset the run's start time, so every elapsed and "
        "every rate is wrong by the length of the preceding stage")


def test_an_explicit_path_still_wins(tmp_path):
    """Carrying forward must not stop a caller that knows better."""
    home = fresh(tmp_path)
    run(home, "start", "--path", "/old/corpus", "--started-by", "cli")
    run(home, "start", "--path", CORPUS, "--started-by", "cli")
    assert marker(home)["path"] == CORPUS


def test_a_beat_with_no_path_keeps_it_too(tmp_path):
    home = fresh(tmp_path)
    run(home, "start", "--path", CORPUS, "--started-by", "cli")
    run(home, "beat")
    assert marker(home)["path"] == CORPUS


def test_a_new_run_after_a_clear_starts_clean(tmp_path):
    """The distinction that makes carrying forward safe.

    A clear removes the marker, so a genuinely new run has nothing to inherit
    and gets its own start time and its own path.
    """
    home = fresh(tmp_path)
    run(home, "start", "--path", "/first/corpus", "--started-by", "cli")
    first = marker(home)["startedAt"]
    assert run(home, "clear").returncode == 0
    assert not (home / "data" / "run").exists()

    assert run(home, "start", "--path", CORPUS, "--started-by", "cli").returncode == 0
    now = marker(home)
    assert now["path"] == CORPUS
    assert now["startedAt"] >= first, "a new run inherited the old one's clock"


def test_the_heartbeat_still_advances_on_a_stage_start(tmp_path):
    """Carrying forward startedAt must not carry forward the heartbeat.

    The heartbeat is the whole liveness signal: Gloss deletes a marker whose
    heartbeat stopped, so a start that refreshed nothing would make a working
    run look dead.
    """
    home = fresh(tmp_path)
    run(home, "start", "--path", CORPUS, "--started-by", "cli")
    first = marker(home)["heartbeatAt"]
    # Force a distinguishable second write rather than racing the clock.
    data = marker(home)
    data["heartbeatAt"] = first - 60000
    (home / "data" / "run").write_text(json.dumps(data))
    run(home, "start", "--path", "", "--started-by", "workflow")
    assert marker(home)["heartbeatAt"] > first - 60000
