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
"""A run executed by daemons must not depend on a terminal to look alive.

The marker's heartbeat had two writers and neither covers a run. The stages beat
only while a stage task is running, so nothing beats between them; and
bin/bigtranslate's wait loop, which would cover the gaps, is a shell in
somebody's terminal.

On the 2026-09-27 corpus run the extract to translate handover took 17m32s
against the ten minute bound in Gloss's ProcessBtWrapper, and no driver shell was
running. Gloss deleted the marker and reported IDLE with 442 translate tasks
queued and healthy. The run was executed entirely by the File Manager, the
Workflow Manager, the Resource Manager and the batch stubs, all daemons.

So liveness is asked of the Workflow Manager, which has non-terminal instances
for exactly as long as there is work. The three rules below matter more than the
beating: what this must never do is claim a run is alive when it is not.
"""
import os
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
HEARTBEAT = BIN / "bt-heartbeat"
OODT = BIN / "oodt"


def home(tmp_path, marker=None, done=False):
    h = tmp_path / "home"
    (h / "data").mkdir(parents=True)
    (h / "bin").mkdir(parents=True)
    (h / "workflow" / "bin").mkdir(parents=True)
    # bt-run-marker is invoked for real, so it has to be there.
    for script in ("bt-run-marker",):
        (h / "bin" / script).write_bytes((BIN / script).read_bytes())
        (h / "bin" / script).chmod(0o755)
    if marker is not None:
        (h / "data" / "run").write_text(json.dumps(marker))
    if done:
        (h / "data" / "run.done").write_text('{"clearedAt": 1}')
    return h


def fake_wmgr(h, output):
    """Stand in for wmgr-client, which is the only thing asked about liveness."""
    client = h / "workflow" / "bin" / "wmgr-client"
    client.write_text("#!/bin/sh\ncat <<'OUT'\n%s\nOUT\n" % output)
    client.chmod(0o755)


def silent_wmgr(h):
    client = h / "workflow" / "bin" / "wmgr-client"
    client.write_text("#!/bin/sh\nexit 1\n")
    client.chmod(0o755)


def beat_once(h):
    env = dict(os.environ)
    env["BIGTRANSLATE_HOME"] = str(h)
    return subprocess.run(["bash", str(HEARTBEAT), "--once"],
                          capture_output=True, text=True, env=env)


def heartbeat_of(h):
    return json.loads((h / "data" / "run").read_text()).get("heartbeatAt")


RUNNING = ("Instance: [id=1, status=Executing, currentTask=x]\n"
           "Instance: [id=2, status=WaitingOnResources, currentTask=y]")
FINISHED = ("Instance: [id=1, status=Success, currentTask=x]\n"
            "Instance: [id=2, status=FINISHED, currentTask=y]")

STALE = {"status": "TRANSLATING", "path": "/corpus", "startedAt": 1,
         "heartbeatAt": 1}


class TestItBeatsARunningPipeline:

    def test_a_marker_is_refreshed_while_instances_run(self, tmp_path):
        h = home(tmp_path, marker=dict(STALE))
        fake_wmgr(h, RUNNING)
        assert beat_once(h).returncode == 0
        assert heartbeat_of(h) > 1, (
            "the heartbeat did not advance, so Gloss will delete a marker for "
            "a run that is working")

    def test_the_rest_of_the_marker_survives(self, tmp_path):
        h = home(tmp_path, marker=dict(STALE))
        fake_wmgr(h, RUNNING)
        beat_once(h)
        after = json.loads((h / "data" / "run").read_text())
        assert after["path"] == "/corpus"
        assert after["startedAt"] == 1


class TestTheThreeRules:
    """Each of these is a way to lie about a run, which is worse than silence."""

    def test_it_never_invents_a_marker(self, tmp_path):
        # No marker means no run was started. A heartbeat is not a reason to
        # decide one was.
        h = home(tmp_path, marker=None)
        fake_wmgr(h, RUNNING)
        assert beat_once(h).returncode == 0
        assert not (h / "data" / "run").exists(), (
            "a run appeared out of nothing")

    def test_it_does_not_beat_past_the_end_of_a_run(self, tmp_path):
        # The join clears the marker as its last act and records run.done.
        h = home(tmp_path, marker=dict(STALE), done=True)
        fake_wmgr(h, RUNNING)
        assert beat_once(h).returncode == 0
        assert heartbeat_of(h) == 1, "a finished run was refreshed"

    def test_it_does_not_beat_when_the_manager_is_silent(self, tmp_path):
        # Harsh and honest: if the Workflow Manager is not answering, the run
        # is not progressing, and a stale marker says so. Guessing the other
        # way is how a marker sat for a day naming the previous corpus.
        h = home(tmp_path, marker=dict(STALE))
        silent_wmgr(h)
        assert beat_once(h).returncode == 0
        assert heartbeat_of(h) == 1


class TestItDoesNotBeatAFinishedPipeline:

    def test_only_terminal_instances_is_not_a_running_run(self, tmp_path):
        h = home(tmp_path, marker=dict(STALE))
        fake_wmgr(h, FINISHED)
        assert beat_once(h).returncode == 0
        assert heartbeat_of(h) == 1

    def test_no_instances_at_all_is_not_a_running_run(self, tmp_path):
        h = home(tmp_path, marker=dict(STALE))
        fake_wmgr(h, "no workflow instances")
        assert beat_once(h).returncode == 0
        assert heartbeat_of(h) == 1


class TestTheStackOwnsIt:

    def test_it_ships_and_is_executable(self):
        assert HEARTBEAT.is_file()
        assert HEARTBEAT.stat().st_mode & 0o111

    def test_the_stack_starts_and_stops_it(self):
        text = OODT.read_text()
        assert "start_heartbeat" in text and "stop_heartbeat" in text
        # Exactly the manager's own start and stop. A compute node has no
        # marker to beat and no Workflow Manager to ask.
        assert text.count("\n  start_heartbeat\n") == 1
        assert text.count("\n  stop_heartbeat\n") == 1

    def test_the_compute_node_path_does_not_start_it(self):
        text = OODT.read_text()
        node = text[text.index('"start-pantogloss"'):text.index('"restart"')]
        assert "start_heartbeat" not in node, (
            "a node would beat a marker that is not its run")

    def test_the_interval_is_well_inside_the_stale_bound(self):
        """Gloss deletes a marker whose heartbeat is over ten minutes old."""
        text = HEARTBEAT.read_text()
        default = int(text.split("BT_HEARTBEAT_INTERVAL:-")[1].split("}")[0])
        assert default * 4 <= 600, (
            "%ds leaves too few beats inside the ten minute bound" % default)

    def test_liveness_is_counted_the_same_way_the_driver_counts_it(self):
        """Two answers to "is it running" that disagree would be worse than one."""
        driver = (BIN / "bigtranslate").read_text()
        beat = HEARTBEAT.read_text()
        terminal = "status=(FINISHED|ERROR|Success|Failure|Stopped)"
        assert terminal in driver
        assert terminal in beat
