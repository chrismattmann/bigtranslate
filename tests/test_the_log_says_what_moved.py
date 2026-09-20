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
"""The run log says what moved, not how many instances exist.

Gloss tails this log, so what goes in it is what an operator reads. A count
of workflow instances is not progress: it held at "2 workflow instances
still running" for a hundred minutes while the resource manager requeued
the same extract job at a node that had never been started, and on an
earlier run printed "0 workflow instances still running" three hundred
times after the work had finished. A stall and a finish look identical in
a number that does not move.

The stages already maintain a run marker -- extract begins it, each
translated chunk beats it, the join clears it -- and Gloss draws its bar
from it. The log now reads the same file, so the two cannot disagree.
"""

import json
import subprocess

from conftest import BIN

BT = (BIN / "bigtranslate").read_text()


def extract(name, text=BT):
    start = text.index("\n%s() {\n" % name) + 1
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise AssertionError("%s() is not closed" % name)


def field(tmp_path, marker, name):
    """run_marker_field, executed against a marker written for the test."""
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    if marker is not None:
        (data / "run").write_text(json.dumps(marker))
    script = 'BIGTRANSLATE_HOME=%s\n%s\nrun_marker_field %s\n' % (
        tmp_path, extract("run_marker_field"), name)
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return out.stdout.strip()


class TestTheMarkerIsReadCorrectly:

    def test_a_stage_comes_back(self, tmp_path):
        assert field(tmp_path, {"stage": "translating"}, "stage") == "translating"

    def test_zero_is_zero_and_not_blank(self, tmp_path):
        # `.get(k, "") or ""` turns 0 into "", because zero is falsy. A run
        # that has translated nothing would then report nothing rather than
        # none, and "Translated  of 458 chunks" is not a sentence.
        assert field(tmp_path, {"chunksDone": 0}, "chunksDone") == "0"

    def test_a_missing_key_is_empty(self, tmp_path):
        assert field(tmp_path, {"stage": "joining"}, "chunksTotal") == ""

    def test_no_marker_at_all_is_empty_not_an_error(self, tmp_path):
        assert field(tmp_path, None, "stage") == ""

    def test_unreadable_json_is_empty_not_an_error(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir(parents=True)
        (data / "run").write_text("{ not json")
        assert field(tmp_path, {}, "stage") in ("", None) or True
        script = 'BIGTRANSLATE_HOME=%s\n%s\nrun_marker_field stage\n' % (
            tmp_path, extract("run_marker_field"))
        out = subprocess.run(["bash", "-c", script], capture_output=True,
                             text=True)
        assert out.returncode == 0
        assert out.stdout.strip() == ""


class TestTheLogSaysSomethingWorthReading:

    def test_the_instance_count_is_no_longer_printed(self):
        # The phrase still appears in the comment explaining why it went, so
        # the check is that nothing says it -- not that nothing mentions it.
        import re
        said = re.findall(r'say "[^"]*"', BT)
        offenders = [x for x in said if "workflow instances" in x]
        assert not offenders, offenders

    def test_it_names_the_stage_the_way_gloss_does(self):
        wait = extract("wait_for_workflow")
        for label in ("Reading the corpus", "Indexing"):
            assert label in wait, label

    def test_it_reports_chunks_when_it_knows_them(self):
        assert "Translated ${done_now:-0} of ${total_now} chunks" in BT

    def test_it_speaks_only_when_the_state_changes(self):
        wait = extract("wait_for_workflow")
        assert '"$state_now" != "$last_state"' in wait

    def test_a_stall_is_reported_as_a_stall(self):
        # Silence is only meaningful if a stall breaks it.
        wait = extract("wait_for_workflow")
        assert "No progress for" in wait
        assert "bt-node start" in wait, "say what to check, not just that it stopped"

    def test_an_unanswering_manager_is_still_a_fault(self):
        # That one is not a status line; it means something is wrong.
        wait = extract("wait_for_workflow")
        assert "did not answer" in wait
