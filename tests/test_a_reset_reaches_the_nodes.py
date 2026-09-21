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
"""A reset resets the cluster, not the machine it was typed on.

bin/bt-reset cleared this machine. The nodes kept whatever the last run had
left them, and bt-translate-chunk skips a chunk whose output already exists,
so a node with old translations does not translate and does not say so.

On 2026-09-20 that happened: a node held 308 translations from eight days
earlier and skipped those chunks. They were catalogued as the new run's own
output. Because the old chunks had different boundaries, 432,630 strings
ended up with no translation anywhere, and the run read as 2.3x faster than
the one it was being compared against -- for having done a third less work.

Two defences, tested here. The reset reaches the nodes, and a chunk whose
translation predates it is refused rather than reused.
"""

import os
import subprocess
import time

import pytest

from conftest import BIN

CLUSTER = BIN / "bt-cluster"
RESET = BIN / "bt-reset"
TRANSLATE = BIN / "bt-translate-chunk"


def fake_ssh(tmp_path):
    """An ssh that runs the command here, so the node is a directory."""
    path = tmp_path / "ssh-here"
    path.write_text('#!/bin/sh\nshift\nexec sh -c "$*"\n')
    path.chmod(0o755)
    return path


def node_home(tmp_path, dirs=("translated", "strings")):
    home = tmp_path / "node"
    for name in dirs:
        (home / "data" / name).mkdir(parents=True)
        (home / "data" / name / "chunk-00000.json").write_text("old")
    return home


def cluster_reset(tmp_path, home):
    (home / "conf").mkdir(parents=True, exist_ok=True)
    (home / "conf" / "nodes.conf").write_text(
        "local   localhost  8\nnode1   node1.invalid  8\n")
    return subprocess.run(
        ["sh", str(CLUSTER), "--home", str(home),
         "--ssh", str(fake_ssh(tmp_path)), "reset"],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})


class TestTheResetReachesTheNodes:

    def test_a_nodes_outputs_are_moved_out_of_the_way(self, tmp_path):
        home = node_home(tmp_path)
        done = cluster_reset(tmp_path, home)
        assert done.returncode == 0, done.stderr
        assert list((home / "data" / "translated").iterdir()) == [], \
            "the node kept outputs a reset should have cleared"

    def test_nothing_is_deleted(self, tmp_path):
        # Moved aside, not removed. The 2026-09-20 diagnosis was only
        # possible because the stale files were still there to be dated.
        home = node_home(tmp_path)
        cluster_reset(tmp_path, home)
        kept = list((home / "data").glob("translated-superseded-*/chunk-*.json"))
        assert len(kept) == 1, sorted(p.name for p in (home / "data").iterdir())
        assert kept[0].read_text() == "old"

    def test_the_directory_is_left_ready_for_the_next_run(self, tmp_path):
        home = node_home(tmp_path)
        cluster_reset(tmp_path, home)
        for name in ("translated", "strings"):
            assert (home / "data" / name).is_dir(), \
                f"data/{name} was moved aside and not recreated"

    def test_an_empty_node_is_not_given_a_superseded_directory(self, tmp_path):
        # Otherwise every reset of a clean cluster litters it with dated
        # empty directories, and the ones that mean something get lost.
        home = tmp_path / "node"
        (home / "data" / "translated").mkdir(parents=True)
        done = cluster_reset(tmp_path, home)
        assert done.returncode == 0, done.stderr
        assert list((home / "data").glob("*-superseded-*")) == []

    def test_a_node_with_no_deployment_is_not_an_error(self, tmp_path):
        # Reset runs before deploy on a fresh cluster.
        home = tmp_path / "nothing-here"
        (home / "conf").mkdir(parents=True)
        (home / "conf" / "nodes.conf").write_text(
            "local  localhost  8\nnode1  node1.invalid  8\n")
        done = subprocess.run(
            ["sh", str(CLUSTER), "--home", str(home),
             "--ssh", str(fake_ssh(tmp_path)), "reset"],
            capture_output=True, text=True,
            env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})
        assert done.returncode == 0, done.stderr


def reset_home(tmp_path, cluster_exit=0):
    """A home whose bin/bt-cluster records that it was called."""
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    (home / "conf").mkdir(parents=True)
    (home / "conf" / "nodes.conf").write_text("local  localhost  8\n")
    called = home / "cluster-was-called"
    (home / "bin" / "bt-cluster").write_text(
        f'#!/bin/sh\necho "$@" > "{called}"\nexit {cluster_exit}\n')
    (home / "bin" / "bt-cluster").chmod(0o755)
    # bt-reset sources this before it does anything.
    (home / "bin" / "setenv.sh").write_text(
        "FILEMGR_PORT=9\nWORKFLOW_PORT=9\n"
        "SOLR_URL=http://localhost:0/solr\n"
        "export FILEMGR_PORT WORKFLOW_PORT SOLR_URL\n")
    return home, called


def run_reset(home, *args):
    env = dict(os.environ)
    env.update(BIGTRANSLATE_HOME=str(home),
               NODES_CONF=str(home / "conf" / "nodes.conf"))
    return subprocess.run(["sh", str(RESET), "--force", "--keep-solr", *args],
                          capture_output=True, text=True, env=env)


class TestBtResetCallsTheCluster:

    def test_it_resets_the_nodes_as_well_as_this_machine(self, tmp_path):
        home, called = reset_home(tmp_path)
        done = run_reset(home)
        assert called.exists(), \
            "bt-reset cleared this machine only: " + done.stdout
        assert called.read_text().strip() == "reset"

    def test_local_only_stays_on_this_machine(self, tmp_path):
        home, called = reset_home(tmp_path)
        done = run_reset(home, "--local-only")
        assert done.returncode == 0, done.stderr
        assert not called.exists()

    def test_a_node_that_could_not_be_cleared_fails_the_reset(self, tmp_path):
        # Reporting success here is how the bad run started. A half-reset
        # cluster must not look like a reset one.
        home, _ = reset_home(tmp_path, cluster_exit=1)
        done = run_reset(home)
        assert done.returncode != 0
        assert "Do not start a run" in done.stdout

    def test_it_runs_to_the_end(self, tmp_path):
        # It did not. PR #120 replaced a hand-written schema file with
        # Mnemosyne's tool and removed the "schema=" assignment, but left
        # the [ -f "$schema" ] test that guarded it. Under set -u that
        # aborts, so bt-reset cleared data/ and then died -- before the
        # Solr index, before the run marker, and before the nodes. It
        # exited 1 having done half the job, and nothing noticed because
        # the deployment was still running an older copy of the script.
        home, _ = reset_home(tmp_path)
        done = run_reset(home)
        assert "unbound variable" not in done.stderr, done.stderr
        assert done.returncode == 0, done.stderr
        assert "next run starts from nothing" in done.stdout

    def test_the_warning_names_the_nodes_before_asking(self, tmp_path):
        home, _ = reset_home(tmp_path)
        done = run_reset(home)
        assert "compute node" in done.stdout


class TestAStaleTranslationIsRefused:

    def translate(self, tmp_path, chunk_age, out_age, *args):
        # --service-url is required by the parser and never reached: the
        # skip decision is made before anything is translated.
        chunk = tmp_path / "chunk-00000.json"
        chunk.write_text('{"docs": []}')
        out = tmp_path / "out" / "chunk-00000.json"
        out.parent.mkdir()
        out.write_text('{"docs": []}')
        now = time.time()
        os.utime(chunk, (now - chunk_age, now - chunk_age))
        os.utime(out, (now - out_age, now - out_age))
        return subprocess.run(
            ["python3", str(TRANSLATE), "--chunk", str(chunk),
             "--out-dir", str(out.parent),
             "--service-url", "http://localhost:0/", *args],
            capture_output=True, text=True)

    def test_an_output_older_than_its_chunk_is_not_reused(self, tmp_path):
        # The chunk was written by this run's staging; the translation
        # predates it, so it is a translation of some other text.
        done = self.translate(tmp_path, chunk_age=10, out_age=10000)
        assert done.returncode == 2, done.stdout + done.stderr
        assert "earlier run" in done.stdout + done.stderr

    def test_an_output_newer_than_its_chunk_is_still_reused(self, tmp_path):
        # Resuming an interrupted run must keep working.
        done = self.translate(tmp_path, chunk_age=10000, out_age=10)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "skipping" in done.stdout + done.stderr

    def test_force_translates_a_stale_chunk_anyway(self, tmp_path):
        done = self.translate(tmp_path, 10, 10000, "--force")
        assert "earlier run" not in done.stdout + done.stderr
