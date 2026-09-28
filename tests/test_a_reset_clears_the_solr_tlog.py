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
"""A reset that deletes the index and keeps the transaction log is not a reset.

Solr replays tlog when a core loads. An index directory that was removed and
a tlog that was not is a core that comes back up holding the previous run's
documents -- after a reset that printed "Cleared the Solr index" on its way
there. On 2026-09-27 the tlog left behind was 49MB.

Nothing about the document count would show it. Every posting is indexed
whether or not its Spanish was translated, so replayed documents are corpus
records like any other and the total reads as the corpus size either way --
which is the same reason a matching count has never verified a run.
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
RESET = BIN / "bt-reset"


def home(tmp_path):
    h = tmp_path / "home"
    (h / "bin").mkdir(parents=True)
    (h / "conf").mkdir(parents=True)
    for d in ("strings", "translated", "translated-catalog", "jobs",
              "winstdb", "run"):
        (h / "data" / d).mkdir(parents=True)
    (h / "filemgr" / "catalog").mkdir(parents=True)
    (h / "bin" / "setenv.sh").write_text(
        "FILEMGR_PORT=9\nWORKFLOW_PORT=9\n"
        "SOLR_URL=http://localhost:0/solr\n"
        "export FILEMGR_PORT WORKFLOW_PORT SOLR_URL\n")
    return h


def solr_data(tmp_path, index=True, tlog=True):
    """A Solr data home shaped like the real one, on its own volume."""
    d = tmp_path / "btsolr"
    if index:
        (d / "index").mkdir(parents=True)
        (d / "index" / "segments_9").write_text("previous run")
    if tlog:
        (d / "tlog").mkdir(parents=True)
        (d / "tlog" / "tlog.0000000000000000042").write_text("previous run")
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_reset(h, data_dir):
    env = dict(os.environ)
    env.update(BIGTRANSLATE_HOME=str(h), SOLR_DATA_DIR=str(data_dir))
    return subprocess.run(
        ["sh", str(RESET), "--force", "--local-only"],
        capture_output=True, text=True, env=env)


def test_the_transaction_log_is_cleared(tmp_path):
    h = home(tmp_path)
    data = solr_data(tmp_path)
    done = run_reset(h, data)
    assert done.returncode == 0, done.stderr
    assert not list((data / "tlog").iterdir()), (
        "the tlog survived the reset, so the core will replay the previous "
        "run's documents into an index the reset just emptied")


def test_the_index_is_still_cleared(tmp_path):
    h = home(tmp_path)
    data = solr_data(tmp_path)
    done = run_reset(h, data)
    assert done.returncode == 0, done.stderr
    assert not list((data / "index").iterdir())


def test_both_directories_survive_as_directories(tmp_path):
    """Removed and recreated, not left missing.

    Solr is started by bin/oodt with -Dsolr.data.home and runs under a
    security policy that grants access to that path and its children by
    name, so the reset leaves the shape it found rather than relying on the
    core to recreate it.
    """
    h = home(tmp_path)
    data = solr_data(tmp_path)
    assert run_reset(h, data).returncode == 0
    assert (data / "index").is_dir()
    assert (data / "tlog").is_dir()


def test_it_says_what_it_cleared(tmp_path):
    h = home(tmp_path)
    data = solr_data(tmp_path)
    out = run_reset(h, data).stdout
    assert "index" in out and "tlog" in out, (
        "a reset that clears the tlog silently is one nobody can tell "
        "cleared it: %s" % out)


def test_a_missing_tlog_is_not_an_error(tmp_path):
    """A first run, or a deployment whose Solr has never started."""
    h = home(tmp_path)
    data = solr_data(tmp_path, tlog=False)
    done = run_reset(h, data)
    assert done.returncode == 0, done.stderr
    assert "nothing to clear" in done.stdout


def test_keep_solr_still_keeps_both(tmp_path):
    h = home(tmp_path)
    data = solr_data(tmp_path)
    env = dict(os.environ)
    env.update(BIGTRANSLATE_HOME=str(h), SOLR_DATA_DIR=str(data))
    done = subprocess.run(
        ["sh", str(RESET), "--force", "--local-only", "--keep-solr"],
        capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    assert (data / "index" / "segments_9").exists(), "--keep-solr cleared the index"
    assert list((data / "tlog").iterdir()), "--keep-solr cleared the tlog"
