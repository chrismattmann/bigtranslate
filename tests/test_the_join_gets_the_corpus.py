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
"""The join does not inherit the run's metadata, so it needs its own CorpusDir.

CorpusDir was removed from the join task on the reading that it "follows the run
metadata emitted by the extract and translation stages". That is true of the
extract, which runs in the instance the driver started with CorpusDir on
EmploymentCorpusReady, and false of the join, which runs in a separate instance
created by EmploymentTranslationsComplete -- and the extract sent that event
bare, so the instance was created with no metadata at all.

The fix is to carry CorpusDir on that event rather than to give the join task a
static default. A default would also have stopped the crash and would have
indexed whatever conf/site.sh named on a run launched against any other
directory: a worse failure than the one it cures, because nothing would say so.

On the 2026-09-27 corpus run PathUtils therefore had nothing to substitute and
left the name as written. All four shards were handed the literal string:

    bt-join-index: error: no .tsv files under [CorpusDir]

The commit-only pass then committed an empty index, the run marker was cleared,
and the workflow recorded Success. Solr held 0 documents at the end of a run
whose 2,286,244 translations were all present and correct.

Three separate things had to hold for that to be reported as a success, and
each is covered here: the task needs the corpus, a placeholder must not be
mistaken for a path, and a failed shard must fail the join.
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "workflow" / "src" / "main" / "resources" / "policy" / "tasks.xml"
JOIN_PGE = (ROOT / "pge" / "src" / "main" / "resources" / "policy" / "no_filter"
            / "PgeConfig_JoinIndex.xml")
JOIN = (ROOT / "distribution" / "src" / "main" / "resources" / "bin"
        / "bt-join-index")


def task(name):
    root = ET.parse(TASKS).getroot()
    for element in root.iter("task"):
        if element.get("name") == name:
            return element
    raise AssertionError("no task named %s" % name)


def properties(name):
    return {p.get("name"): p.get("value")
            for p in task(name).iter("property")}


EXTRACT_PGE = (ROOT / "pge" / "src" / "main" / "resources" / "policy"
               / "no_filter" / "PgeConfig_ExtractStrings.xml")


def join_event_command():
    text = EXTRACT_PGE.read_text()
    cmds = [c for c in re.findall(r"<cmd>(.*?)</cmd>", text, re.S)
            if "EmploymentTranslationsComplete" in c]
    assert cmds, "nothing fires the event that starts the join"
    return cmds[0]


def test_the_join_event_carries_the_corpus():
    cmd = join_event_command()
    assert "--metaData" in cmd and "--key CorpusDir" in cmd, (
        "the event that creates the join's instance carries no CorpusDir, so "
        "PathUtils leaves the literal [CorpusDir] in the join command and "
        "every shard exits on it")


def test_it_is_the_run_value_and_not_the_environment():
    """Passed on from the extract's own CorpusDir, not read from site.sh."""
    cmd = join_event_command()
    assert '--key CorpusDir "[CorpusDir]"' in cmd
    assert "BIGTRANSLATE_CORPUS" not in cmd, (
        "taking the corpus from the deployment environment here would index "
        "the wrong directory, silently, on a run launched against another one")


def test_neither_task_gets_a_static_corpus():
    """The corpus stays per run on both sides of the handover.

    A static default in tasks.xml would stop the crash and reintroduce exactly
    what moving CorpusDir into run metadata was for.
    """
    for name in ("Extract_Strings_Task", "Join_Index_Task"):
        assert "CorpusDir" not in properties(name), name


class TestAPlaceholderIsNotAPath:

    def run_join(self, corpus):
        return subprocess.run(
            [sys.executable, str(JOIN), "--corpus", corpus,
             "--translated", "/tmp/nothing", "--translations-db", "/tmp/n.sqlite",
             "--solr-url", "http://localhost:1/solr", "--colheaders", "/tmp/n",
             "--translate-cols", "x"],
            capture_output=True, text=True)

    def test_an_unsubstituted_name_is_refused_as_such(self):
        done = self.run_join("[CorpusDir]")
        assert done.returncode != 0
        assert "unsubstituted" in done.stderr, (
            "the message describes the placeholder as a path, which sends "
            "whoever reads it to the corpus: %s" % done.stderr[-200:])
        assert "policy problem" in done.stderr

    def test_a_real_missing_directory_still_says_so(self):
        """The guard must not swallow the ordinary case."""
        done = self.run_join("/tmp/definitely-not-a-corpus-here")
        assert "no .tsv files under" in done.stderr
        assert "unsubstituted" not in done.stderr


class TestAFailedShardFailsTheJoin:

    def shard_command(self):
        text = JOIN_PGE.read_text()
        cmds = [c for c in re.findall(r"<cmd>(.*?)</cmd>", text, re.S)
                if 'pids=""' in c]
        assert cmds, "the shard loop no longer collects pids"
        return (cmds[0].replace("[GreaterThan]", ">").replace("[Ampersand]", "&")
                .replace("[JoinShards]", "4")
                .replace("[JobLogDir]/join_[DateMilis].log", "/dev/null"))

    def with_shard(self, program):
        cmd = self.shard_command().replace(
            '"[BIGTRANSLATE_HOME]/bin/bt-join-index"', program)
        cmd = re.sub(r"--corpus .*?--expect \$EXPECTED", "", cmd)
        return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)

    def test_a_bare_wait_is_not_used(self):
        """It returns 0 whatever the background jobs did."""
        assert "done; wait</cmd>" not in JOIN_PGE.read_text(), (
            "a bare wait hides every shard failure")

    def test_a_failing_shard_fails_the_command(self):
        done = self.with_shard("false")
        assert done.returncode != 0, (
            "four dead shards reported success, and the commands after this "
            "one committed an empty index and cleared the run marker")
        assert "a join shard failed" in done.stderr

    def test_succeeding_shards_still_succeed(self):
        assert self.with_shard("true").returncode == 0

    def test_the_clear_comes_after_the_shards(self):
        """So a failed join cannot report itself finished.

        The marker clear and the commit are both after the shard loop, which
        now exits non-zero, and the PGE stops on a failed command.
        """
        text = JOIN_PGE.read_text()
        assert text.index('pids=""') < text.index("bt-run-marker")
        assert text.index('pids=""') < text.index("--commit-only")
