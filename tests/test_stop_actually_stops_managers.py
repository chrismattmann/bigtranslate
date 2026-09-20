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
"""A free port is not a stopped process.

wait_for_stopped watches ports. A manager that closes its listener and does
not exit passes it, keeps its pid file, and the next start reads that file,
finds the pid alive, and refuses:

    File Manager is already running (pid 60719). Start aborted.

Nothing is then listening on 9200 and nothing ever will be, because what
blocks the start is the corpse of what should have stopped. On 2026-09-20
that held a run for a hundred minutes: the managers came up without a File
Manager, the resource manager had a node it could not reach, and it
requeued the same extract job every cycle while the driver sat in
"Translating" with nothing to translate.

These tests run stop_lingering_managers against real processes. Asserting
that the script contains "kill -9" would pass against a version that never
reaches it.
"""

import os
import signal
import subprocess
import time

from conftest import BIN

OODT = (BIN / "oodt").read_text()


def extract(name, text=OODT):
    """One shell function, lifted out so it can be run on its own."""
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


def run_stop(tmp_path, pids):
    """stop_lingering_managers, with the three pid files pointing at `pids`."""
    homes = {"FILEMGR_HOME": "filemgr", "WORKFLOW_HOME": "workflow",
             "RESMGR_HOME": "resmgr"}
    names = {"filemgr": "cas.filemgr.pid", "workflow": "cas.workflow.pid",
             "resmgr": "cas.resmgr.pid"}
    env = []
    files = {}
    for var, sub in homes.items():
        run = tmp_path / sub / "run"
        run.mkdir(parents=True, exist_ok=True)
        env.append('%s=%s' % (var, tmp_path / sub))
        files[sub] = run / names[sub]
    for sub, pid in pids.items():
        if pid is not None:
            files[sub].write_text(str(pid))
    script = "%s\n%s\n%s\nstop_lingering_managers\n" % (
        "\n".join("export " + e for e in env),
        extract("manager_pid_files"),
        extract("stop_lingering_managers"),
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return out, files


def spawn():
    """A process that ignores nothing and will sit until it is ended."""
    return subprocess.Popen(["sleep", "300"])


class TestALingeringManagerIsEnded:

    def test_a_live_pid_is_killed_and_its_file_removed(self, tmp_path):
        proc = spawn()
        try:
            out, files = run_stop(tmp_path, {"filemgr": proc.pid})
            assert "still running" in out.stdout, out.stdout
            proc.wait(timeout=30)
            assert proc.poll() is not None, "the process outlived stop"
            assert not files["filemgr"].exists(), "the pid file was left behind"
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_every_manager_is_checked_not_just_the_first(self, tmp_path):
        procs = {k: spawn() for k in ("filemgr", "workflow", "resmgr")}
        try:
            out, files = run_stop(
                tmp_path, {k: p.pid for k, p in procs.items()})
            for name, p in procs.items():
                p.wait(timeout=30)
                assert p.poll() is not None, "%s survived" % name
                assert not files[name].exists(), "%s pid file left" % name
        finally:
            for p in procs.values():
                if p.poll() is None:
                    p.kill()

    def test_a_dead_pid_leaves_no_file_and_no_noise(self, tmp_path):
        proc = spawn()
        proc.kill()
        proc.wait(timeout=10)
        out, files = run_stop(tmp_path, {"workflow": proc.pid})
        assert not files["workflow"].exists()
        assert "still running" not in out.stdout

    def test_a_junk_pid_file_is_removed_rather_than_obeyed(self, tmp_path):
        # A truncated or half-written file must not become a kill argument.
        homes = tmp_path / "resmgr" / "run"
        homes.mkdir(parents=True)
        (homes / "cas.resmgr.pid").write_text("not-a-pid\n")
        out, files = run_stop(tmp_path, {})
        assert not files["resmgr"].exists()
        assert out.returncode == 0

    def test_no_pid_file_at_all_is_fine(self, tmp_path):
        out, _ = run_stop(tmp_path, {})
        assert out.returncode == 0


class TestStopCallsIt:

    def test_stop_oodt_ends_lingering_managers(self):
        stop = extract("stop_oodt")
        assert "stop_lingering_managers" in stop

    def test_it_runs_after_the_ports_are_waited_on(self):
        # Most managers release the port and exit; this is for the one that
        # does only the first, so it belongs after the wait rather than
        # instead of it.
        stop = extract("stop_oodt")
        assert stop.index("wait_for_stopped") < stop.index(
            "stop_lingering_managers")

    def test_the_wait_result_still_decides_the_exit_status(self):
        # restart does `stop_oodt || exit 1`, so a stop that could not free a
        # port must still fail even though the tidy-up afterwards succeeded.
        stop = extract("stop_oodt")
        assert "return $rc" in stop
