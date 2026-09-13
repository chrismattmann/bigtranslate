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
"""A quiet workflow manager is not a finished run.

A PGE job script is started by the batch stub and detaches from it, so the
task is marked Success when the script is handed off rather than when its
work is done. The join is where that shows. Caught on run 6, live:

    Instance: [id=3, status=Success,
               currentTask=urn:bigtranslate:Join_Index_Task,
               workflow=JoinIndexWorkflow]

    $ pgrep -f bin/bt-join-index | wc -l
    4

All 1,838 instances read Success while four shards were still writing, with
about two thirds of the index left to go. With nothing else running the wait
loop announces "Workflow finished" and clears the run marker: Gloss drops
the progress pane and shows IDLE, and the log it displays says the run is
over. The index still finishes correctly -- what is wrong is every report
about it, which is the failure this pipeline keeps having.
"""
import subprocess

from conftest import BIN

DRIVER = BIN / "bigtranslate"


def _function(name):
    body = subprocess.run(
        ["sed", "-n", "/^%s() {/,/^}/p" % name, str(DRIVER)],
        capture_output=True, text=True, check=True).stdout
    assert body.strip(), "no %s() in bigtranslate" % name
    return body


class TestTheRunIsNotOverWhileAStageIsWorking:

    def test_there_is_a_check_at_all(self):
        assert "stage_processes_running" in DRIVER.read_text()

    def test_it_gates_the_finish(self):
        body = _function("wait_for_workflow")
        finish = body.index('say "Workflow finished')
        guard = body.index("stage_processes_running")
        assert guard < finish, (
            "the run is announced finished before anything asks whether a "
            "stage is still running")

    def test_the_join_is_one_of_the_stages_watched(self):
        body = _function("stage_processes_running")
        assert "bt-join-index" in body, (
            "the join is the stage that outlives its instance by an hour")

    def test_the_extract_is_watched_too(self):
        body = _function("stage_processes_running")
        assert "bt-extract-strings" in body

    def test_it_matches_this_deployment_not_any_bigtranslate(self):
        # Two deployments on one machine would otherwise wait on each other.
        body = _function("stage_processes_running")
        assert "$BIGTRANSLATE_HOME/bin/" in body, body

    def test_quiet_is_reset_rather_than_the_finish_merely_skipped(self):
        # Skipping the return without resetting quiet would announce the run
        # finished on the very next poll, which is the same bug one poll later.
        body = _function("wait_for_workflow")
        guard = body.index("stage_processes_running")
        after = body[guard:body.index('say "Workflow finished')]
        assert "quiet=0" in after, after

    def test_it_says_why_it_is_still_waiting(self):
        # Silence here reads as a hung run: the manager reports nothing
        # running and the script sits there.
        body = _function("wait_for_workflow")
        assert "still" in body and "stage" in body.lower()

    def test_it_does_not_say_it_every_poll(self):
        # Every fifteen seconds for an hour would push the rest of the log
        # out of the pane Gloss shows.
        body = _function("wait_for_workflow")
        assert "said_waiting_on_stages" in body
