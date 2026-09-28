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
"""A join must not be able to report success over an index nobody can query.

Three runs in a row did exactly that, and no one cheap check would have caught
all of them:

- the shards were handed an unsubstituted [CorpusDir] and all four exited at
  once. Nothing was posted and nothing committed, so "Solr equals what the
  shards posted" is 0 == 0 and passes. What gives it away is that no shard ever
  reported a count.
- the shards indexed all 119,453,210 records and a stray exit ended the script
  before the commit, so every document was in the index and invisible. Every
  shard reported; Solr said 0.
- and the document count cannot arbitrate, because every posting is indexed
  whether or not its Spanish was translated: a run that translates nothing
  produces the same 119,453,210 documents as a good one.

So the invariant is all three of: every shard finished and said what it put in,
the total is not zero, and Solr agrees with the total.
"""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
JOIN = BIN / "bt-join-index"
PGE_DIR = ROOT / "pge" / "src" / "main" / "resources" / "policy" / "no_filter"
JOIN_PGE = PGE_DIR / "PgeConfig_JoinIndex.xml"


class FakeSolr:
    """Answers the one query --verify-only makes."""

    def __init__(self, numFound):
        import http.server
        import threading
        count = numFound

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"response": {"numFound": count}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/solr/bigtranslate" % \
            self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


def home(tmp_path, posted=None):
    h = tmp_path / "home"
    (h / "data" / "join-progress").mkdir(parents=True)
    for shard, count in (posted or {}).items():
        (h / "data" / "join-progress" / ("shard-%d.posted" % shard)).write_text(
            "%d\n" % count)
    return h


def said(done):
    """Everything the run printed. log() goes to stderr, not stdout."""
    return done.stdout + done.stderr


def verify(h, solr_url, of=4):
    env = dict(os.environ)
    env["BIGTRANSLATE_HOME"] = str(h)
    return subprocess.run(
        [sys.executable, str(JOIN), "--verify-only",
         "--corpus", "/tmp", "--translated", "/tmp",
         "--translations-db", "/tmp/x.sqlite", "--solr-url", solr_url,
         "--colheaders", "/tmp/c", "--translate-cols", "/tmp/t", "--of", str(of)],
        capture_output=True, text=True, env=env)


@pytest.fixture
def solr():
    made = []

    def make(numFound):
        s = FakeSolr(numFound)
        made.append(s)
        return s
    yield make
    for s in made:
        s.close()


# The real counts from the 2026-09-28 run.
REAL = {0: 29756381, 1: 29856057, 2: 29969704, 3: 29871068}
TOTAL = sum(REAL.values())          # 119,453,210


def test_it_passes_when_solr_holds_what_the_shards_posted(tmp_path, solr):
    done = verify(home(tmp_path, REAL), solr(TOTAL).url)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "verified: %d documents" % TOTAL in said(done)


def test_a_shard_that_never_finished_fails_it(tmp_path, solr):
    """The shape of the unsubstituted-corpus run: nothing posted, nothing
    committed, so a bare equality check would have passed on 0 == 0."""
    done = verify(home(tmp_path, {}), solr(0).url)
    assert done.returncode == 1
    assert "4 of 4 shards never reported" in said(done)


def test_one_missing_shard_fails_it(tmp_path, solr):
    partial = dict(REAL)
    del partial[2]
    done = verify(home(tmp_path, partial), solr(sum(partial.values())).url)
    assert done.returncode == 1
    assert "missing shard 2" in said(done)


def test_an_uncommitted_index_fails_it(tmp_path, solr):
    """The shape of the truncated-script run: every record posted, none visible."""
    done = verify(home(tmp_path, REAL), solr(0).url)
    assert done.returncode == 1
    assert "posted %d records and Solr holds 0" % TOTAL in said(done)
    assert "never committed" in said(done)


def test_every_shard_reporting_zero_fails_it(tmp_path, solr):
    done = verify(home(tmp_path, {0: 0, 1: 0, 2: 0, 3: 0}), solr(0).url)
    assert done.returncode == 1
    assert "posted nothing" in said(done)


def test_a_surplus_fails_it_and_says_why(tmp_path, solr):
    """More in Solr than this run posted means the index was not emptied."""
    done = verify(home(tmp_path, REAL), solr(TOTAL + 1000).url)
    assert done.returncode == 1
    assert "not empty when the run began" in said(done)


def test_an_unreachable_solr_fails_it(tmp_path):
    done = verify(home(tmp_path, REAL), "http://127.0.0.1:1/solr/bigtranslate")
    assert done.returncode == 1
    assert "could not ask Solr" in said(done)


class TestTheWorkflowRunsIt:

    def cmds(self):
        return re.findall(r"<cmd>(.*?)</cmd>", JOIN_PGE.read_text(), re.S)

    def test_the_join_verifies_before_it_clears_the_marker(self):
        cmds = self.cmds()
        order = [i for i, c in enumerate(cmds)]
        verify_at = next(i for i, c in enumerate(cmds) if "--verify-only" in c)
        commit_at = next(i for i, c in enumerate(cmds) if "--commit-only" in c)
        clear_at = next(i for i, c in enumerate(cmds) if "bt-run-marker" in c)
        assert commit_at < verify_at < clear_at, (
            "verify must come after the commit and before the marker clear, "
            "or a failed join still reports itself finished")

    def test_it_is_given_the_shard_count(self):
        verify_cmd = next(c for c in self.cmds() if "--verify-only" in c)
        assert "--of [JoinShards]" in verify_cmd, (
            "without --of it cannot tell how many shards should have reported")


class TestEveryPgeConfigIsWellFormed:
    """An XML comment cannot contain a double hyphen.

    Which is easy to write by accident in this project, because the commands
    being explained are full of flags: "--verify-only", "--commit-only",
    "--expect". It has broken a build four times. A parse check alone does not
    say why, so this names the rule.
    """

    @pytest.mark.parametrize("path", sorted(PGE_DIR.glob("PgeConfig_*.xml")),
                             ids=lambda p: p.name)
    def test_it_parses(self, path):
        ET.parse(path)

    @pytest.mark.parametrize("path", sorted(PGE_DIR.glob("PgeConfig_*.xml")),
                             ids=lambda p: p.name)
    def test_no_comment_contains_a_double_hyphen(self, path):
        for comment in re.findall(r"<!--(.*?)-->", path.read_text(), re.S):
            assert "--" not in comment, (
                "XML forbids a double hyphen inside a comment, so this file "
                "will not parse. Write the flag without its leading dashes: "
                "%r" % comment[:160])
