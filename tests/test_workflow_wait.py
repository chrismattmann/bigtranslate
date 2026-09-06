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
"""The run ends when the work does.

"grep -c" exits 1 when it counts nothing, so a "|| echo 0" fallback fires on
exactly the case it was written to report and appends a second line. The
count became "0\\n0", the caller compared it against "0", and a run whose
translations had finished in forty-eight minutes sat in its wait loop for
another three hours announcing "0 workflow instances still running".
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "distribution" / "src" / "main" / "resources" / "bin" / "bigtranslate"


def count_with(instance_listing):
    """Run running_instance_count against a stub wmgr-client."""
    body = subprocess.run(
        ["sed", "-n", "/^running_instance_count() {/,/^}/p", str(DRIVER)],
        capture_output=True, text=True, check=True).stdout
    assert body.strip(), "running_instance_count is not in the driver script"
    stub = (
        'BIGTRANSLATE_HOME=$PWD\n'
        'CLIENT_URL=stub\n'
        'mkdir -p workflow/bin\n'
        'cat > workflow/bin/wmgr-client <<"STUB"\n'
        '#!/bin/bash\n'
        'cat <<"LISTING"\n'
        + instance_listing +
        '\nLISTING\n'
        'STUB\n'
        'chmod +x workflow/bin/wmgr-client\n'
    )
    result = subprocess.run(["bash", "-c", stub + body + "\nrunning_instance_count\n"],
                            capture_output=True, text=True, cwd="/tmp")
    return result.stdout


def test_nothing_running_counts_as_zero_on_one_line():
    """The whole bug: the answer has to be usable by "=" against "0"."""
    out = count_with("id=a status=FINISHED\nid=b status=FINISHED")
    assert out == "0\n", (
        "expected a single '0', got %r -- a caller comparing this to '0' "
        "never matches and waits out a finished run" % out)


def test_running_instances_are_counted():
    out = count_with(
        "id=a status=FINISHED\nid=b status=PGE\nid=c status=QUEUED")
    assert out == "2\n", "expected '2', got %r" % out


def test_every_terminal_status_is_excluded():
    out = count_with("\n".join(
        "id=%d status=%s" % (i, s) for i, s in enumerate(
            ["FINISHED", "ERROR", "Success", "Failure", "Stopped"])))
    assert out == "0\n", "a terminal status is being counted as running"


def test_an_unanswered_manager_is_not_reported_as_finished():
    """Silence is not completion.

    Reporting zero for an unreachable manager ends the run early and calls a
    partial corpus a finished one.
    """
    out = count_with("")
    assert out.strip() == "unknown", (
        "an empty answer reported as %r; a run would end on one bad poll"
        % out.strip())


def test_the_wait_loop_stops_on_a_clean_zero():
    """The fix is only useful if the loop it feeds actually exits."""
    source = DRIVER.read_text()
    body = source[source.index("wait_for_workflow() {"):]
    body = body[:body.index("\n}\n") + 3]
    script = (
        'TRANSLATE_TIMEOUT=100\nTRANSLATE_POLL=1\n'
        'say() { echo "$@"; }\n'
        # A file, not a variable: the caller reads this through $(...), and
        # a subshell's increment is lost the moment it exits.
        'C=$(mktemp)\n'
        'echo 0 > "$C"\n'
        'running_instance_count() {\n'
        '  n=$(( $(cat "$C") + 1 )); echo "$n" > "$C"\n'
        '  if [ "$n" -le 2 ]; then echo 3; else echo 0; fi\n'
        '}\n'
        + body +
        '\nwait_for_workflow && echo EXITED_CLEANLY\n'
    )
    result = subprocess.run(["bash", "-c", script],
                            capture_output=True, text=True, timeout=60)
    assert "EXITED_CLEANLY" in result.stdout, (
        "the wait loop never returned:\n%s" % result.stdout[-500:])
    assert "Workflow finished" in result.stdout


def test_the_wait_loop_does_not_stop_while_the_manager_is_silent():
    source = DRIVER.read_text()
    body = source[source.index("wait_for_workflow() {"):]
    body = body[:body.index("\n}\n") + 3]
    script = (
        'TRANSLATE_TIMEOUT=4\nTRANSLATE_POLL=1\n'
        'say() { echo "$@"; }\n'
        'running_instance_count() { echo unknown; }\n'
        + body +
        '\nwait_for_workflow && echo EXITED_CLEANLY\n'
    )
    result = subprocess.run(["bash", "-c", script],
                            capture_output=True, text=True, timeout=60)
    assert "EXITED_CLEANLY" not in result.stdout, (
        "a silent manager ended the run as though it had finished")
