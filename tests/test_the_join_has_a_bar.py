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
"""The join reports where it has got to.

It is the last stage of a run with no bar, and the longest after the corpus
read: an hour and a half on the full corpus, during which Solr holds every
document uncommitted and so reads as empty. The panel drew the chunk
counts, which by then are 458 of 458, so the bar sat full while the index
was being built -- indistinguishable from finished, or from hung.

Four shards index interleaved slices, so no one of them knows the total.
Each writes only its own count and the marker adds them up.
"""

import json
import os
import subprocess
import sys

import pytest

from conftest import BIN

MARKER = BIN / "bt-run-marker"


def home(tmp_path, made=4, done=4):
    """A deployment whose stage the marker will read as joining."""
    h = tmp_path / "home"
    for name in ("strings", "translated", "translated-catalog"):
        (h / "data" / name).mkdir(parents=True)
    for i in range(made):
        (h / "data" / "strings" / ("chunk-%05d.json" % i)).write_text("{}")
    for i in range(done):
        (h / "data" / "translated" / ("chunk-%05d.json" % i)).write_text("{}")
    return h


def shard(h, number, done, total):
    folder = h / "data" / "join-progress"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("shard-%d" % number)).write_text("%d %d\n" % (done, total))


def beat(h):
    env = dict(os.environ)
    env["BIGTRANSLATE_HOME"] = str(h)
    done = subprocess.run([sys.executable, str(MARKER), "beat"],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return json.loads((h / "data" / "run").read_text())


class TestTheShardsAreAddedUp:

    def test_the_marker_sums_every_shard(self, tmp_path):
        h = home(tmp_path)
        for n, count in enumerate([120, 130, 110, 140]):
            shard(h, n, count, 701)
        state = beat(h)
        assert state["stage"] == "joining"
        assert state["filesDone"] == 500
        assert state["filesTotal"] == 2804

    def test_one_shard_alone_is_not_the_whole_run(self, tmp_path):
        # The bug this shape avoids: a shard writing the pair itself would
        # race the others and the bar would jump between their positions.
        h = home(tmp_path)
        shard(h, 0, 120, 701)
        state = beat(h)
        assert state["filesDone"] == 120
        assert state["filesTotal"] == 701

    def test_a_shard_caught_mid_write_is_skipped_not_fatal(self, tmp_path):
        h = home(tmp_path)
        shard(h, 0, 120, 701)
        (h / "data" / "join-progress" / "shard-1").write_text("")
        state = beat(h)
        assert state["filesDone"] == 120

    def test_a_dead_shard_stops_contributing(self, tmp_path):
        # Understating a run that has lost a shard is the right way round.
        h = home(tmp_path)
        shard(h, 0, 200, 701)
        shard(h, 1, 200, 701)
        state = beat(h)
        assert state["filesDone"] == 400
        (h / "data" / "join-progress" / "shard-1").unlink()
        assert beat(h)["filesDone"] == 200


class TestItOnlyAppliesToTheJoin:

    def test_a_translating_run_still_reports_chunks(self, tmp_path):
        # Half the chunks translated: the stage is translating, and the
        # chunk counts are what the panel should draw.
        h = home(tmp_path, made=4, done=2)
        shard(h, 0, 999, 999)
        state = beat(h)
        assert state["stage"] == "translating"
        assert "filesDone" not in state

    def test_no_shard_files_leaves_the_marker_alone(self, tmp_path):
        h = home(tmp_path)
        state = beat(h)
        assert state["stage"] == "joining"
        assert "filesDone" not in state


class TestTheResetClearsIt:

    def test_stale_shard_counts_do_not_reach_the_next_run(self, tmp_path):
        reset = BIN / "bt-reset"
        h = tmp_path / "home"
        (h / "bin").mkdir(parents=True)
        for d in ("strings", "translated", "translated-catalog", "jobs",
                  "winstdb", "run"):
            (h / "data" / d).mkdir(parents=True)
        (h / "filemgr" / "catalog").mkdir(parents=True)
        shard(h, 0, 700, 701)
        (h / "bin" / "setenv.sh").write_text(
            "FILEMGR_PORT=9\nWORKFLOW_PORT=9\n"
            "SOLR_URL=http://localhost:0/solr\n"
            "export FILEMGR_PORT WORKFLOW_PORT SOLR_URL\n")
        env = dict(os.environ)
        env["BIGTRANSLATE_HOME"] = str(h)
        done = subprocess.run(
            ["sh", str(reset), "--force", "--keep-solr", "--local-only"],
            capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr
        assert not (h / "data" / "join-progress").exists()
