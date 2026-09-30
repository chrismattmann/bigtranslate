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
"""A Windows node's services are started by PowerShell, not by bin/bt-node.

bin/bt-node is bash and cannot manage processes on Windows. Four separate things
it relies on are absent or behave differently there, each measured on paparadelle
on 2026-09-30:

- java wants Windows paths and ";" between classpath entries. Given the POSIX
  form it reported "Could not find or load main class ...AvroRpcBatchStub" with
  all 103 jars present, because not one entry resolved.
- "nohup java ... &" does not survive the ssh session that started it: MSYS
  cannot hand a child to the system the way setsid does.
- reading a pid back through a pipe hangs the caller, because a command
  substitution waits for every writer to close stdout and the detached child
  holds it open.
- lsof does not exist, so port_owner, port_taken and port_free are all dead:
  bt-node can neither confirm a start nor find what to stop.

bin/oodt.ps1 had already answered all four for the managers, so the stub became
one more managed service there rather than four reimplementations in bash. The
Unix nodes keep bin/bt-node untouched.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
CLUSTER = BIN / "bt-cluster"
PS1 = BIN / "oodt.ps1"
NODE = BIN / "bt-node"


class TestTheClusterPicksTheRightScript:

    def test_it_asks_the_node_what_it_is(self):
        """Rather than a field in conf/nodes.conf.

        One fewer thing to get wrong, and the answer cannot drift from the
        machine it describes.
        """
        text = CLUSTER.read_text()
        assert "node_is_windows()" in text
        assert "uname -s" in text
        for marker in ("MINGW*", "MSYS*", "CYGWIN*"):
            assert marker in text, marker

    def test_a_windows_node_goes_through_powershell(self):
        text = CLUSTER.read_text()
        start = text[text.index("start_one() {"):text.index("stop_one() {")]
        assert "oodt.ps1 start-node" in start
        assert "bt-node start" in start, "the Unix path is gone"

    def test_a_unix_node_still_goes_through_bt_node(self):
        text = CLUSTER.read_text()
        stop = text[text.index("stop_one() {"):]
        assert "bt-node stop" in stop
        assert "oodt.ps1 stop-node" in stop


class TestTheNodeIsToldTheClusterSPorts:
    """oodt.ps1 derives every URL from its parameters and never reads site.sh.

    It is written for a standalone Windows install: pantogloss on 8765, the File
    Manager on 9000. This deployment uses 8766 and 9200. On the first attempt
    Start-Node waited ten minutes for a translation service on 8765 while the one
    it had just started answered on 8766.
    """

    def test_the_ports_are_passed_from_the_manager(self):
        text = CLUSTER.read_text()
        assert "windows_node_arguments()" in text
        args = text[text.index("windows_node_arguments()"):]
        args = args[:args.index("\n}")]
        assert "-PantoglossPort" in args
        assert "-NodePort" in args
        assert "PANTOGLOSS_PORT" in args, (
            "the port must come from the manager's environment, not a literal")

    def test_both_start_and_stop_pass_them(self):
        text = CLUSTER.read_text()
        for name in ("start_one", "stop_one"):
            body = text[text.index("%s() {" % name):]
            body = body[:body.index("\n}")]
            assert "windows_node_arguments" in body, name


class TestTheStartIsDispatchedAndThenVerified:
    """Windows OpenSSH holds the channel until the session's job object empties.

    Start-Process leaves its children in that job and PowerShell cannot ask for
    CREATE_BREAKAWAY_FROM_JOB, so a plain ssh never returns even once the work is
    done -- measured at 400 seconds still waiting, with both "pantogloss started
    on port 8766" and "Batch stub started on 2001" already in its output.
    """

    def start_body(self):
        text = CLUSTER.read_text()
        return text[text.index("start_one() {"):text.index("stop_one() {")]

    def test_the_dispatch_does_not_wait_on_the_channel(self):
        assert "$SSH -n -f" in self.start_body(), (
            "a plain ssh never returns for a Windows node")

    def test_the_result_is_read_from_the_node_s_ports(self):
        text = CLUSTER.read_text()
        assert "wait_for_node_ports" in text
        assert "node_ports_up" in text
        body = self.start_body()
        assert "wait_for_node_ports" in body

    def test_a_node_that_does_not_come_up_says_so(self):
        body = self.start_body()
        assert "DID NOT COME UP" in body, (
            "a dispatched start that failed would otherwise be silent")

    def test_both_ports_are_checked(self):
        text = CLUSTER.read_text()
        check = text[text.index("node_ports_up()"):]
        check = check[:check.index("\n}")]
        assert "BIGTRANSLATE_NODE_PORT" in check, "the batch stub is not checked"
        assert "PANTOGLOSS_PORT" in check, "the translation service is not checked"


class TestThePowerShellSide:

    def test_the_node_commands_exist_and_are_accepted(self):
        text = PS1.read_text()
        validate = next(l for l in text.splitlines() if "ValidateSet" in l)
        for command in ("start-node", "stop-node"):
            assert command in validate, (
                "%s is rejected by the parameter's ValidateSet" % command)
            assert "'%s' {" % command in text, "%s has no branch" % command

    def test_the_batch_stub_is_a_managed_service(self):
        """So Start-ManagedProcess, Wait-Port and the state file all apply."""
        text = PS1.read_text()
        stub = text[text.index("function Start-BatchStub"):]
        stub = stub[:stub.index("\nfunction ")]
        assert "Start-ManagedProcess 'batchstub'" in stub
        assert "Wait-Port $NodePort" in stub, (
            "bound, not merely launched: a pid that never took its port sent an "
            "afternoon of jobs to a process that was not serving")
        assert "Save-State" in stub

    def test_the_classpath_is_in_the_form_java_wants(self):
        text = PS1.read_text()
        stub = text[text.index("function Start-BatchStub"):]
        stub = stub[:stub.index("\nfunction ")]
        assert "-join ';'" in stub, "java on Windows needs ';' between entries"
        assert "Replace(" in stub and "'/'" in stub, (
            "the deployment root is not converted to forward slashes, which "
            "survive a shell without being read as escapes")

    def test_no_reserved_variable_is_assigned(self):
        """$home is read-only in PowerShell.

        Assigning to it failed the whole script with "Cannot overwrite variable
        HOME because it is read-only or constant."
        """
        text = PS1.read_text()
        assert not re.search(r"^\s*\$home\s*=", text, re.M), (
            "$home is a read-only automatic variable")

    def test_the_deployment_root_survives_an_empty_psscriptroot(self):
        """It is empty when a non-PowerShell parent uses a relative -File path.

        Which is how bin/bt-cluster calls it over ssh: Split-Path was handed an
        empty string and refused it.
        """
        text = PS1.read_text()
        param = text[:text.index("$ErrorActionPreference")]
        assert "Get-Location" in param, (
            "there is no fallback when PSScriptRoot is empty")
        assert "MyInvocation.MyCommand.Path" in param

    def test_starting_a_node_is_idempotent(self):
        """bt-cluster start runs against the whole cluster.

        Start-Pantogloss throws when the port is taken, which is right for a
        whole stack and wrong here: the first version reported "Port 8766 is
        already in use" about the service it had started a minute earlier.
        """
        text = PS1.read_text()
        node = text[text.index("function Start-Node"):]
        node = node[:node.index("\nfunction ")]
        assert "Test-Port $PantoglossPort" in node
        assert "already listening" in node

    def test_stopping_a_node_stops_both_services(self):
        text = PS1.read_text()
        node = text[text.index("function Stop-Node"):]
        node = node[:node.index("\nfunction ")]
        assert "Stop-ManagedProcess 'batchstub'" in node
        assert "Stop-ManagedProcess 'pantogloss'" in node


class TestBtNodeIsUnchangedForUnix:
    """The bash node manager keeps working exactly as it did.

    Three attempts were made to teach it Windows -- path conversion, a
    PowerShell launch, a pid file -- and each uncovered another POSIX assumption
    underneath. None of them is here.
    """

    def test_it_does_not_try_to_handle_windows(self):
        text = NODE.read_text()
        for marker in ("MINGW", "MSYS", "CYGWIN", "cygpath", "powershell"):
            assert marker not in text, (
                "bt-node is the Unix path; %s belongs in oodt.ps1" % marker)

    def test_it_still_uses_a_posix_classpath(self):
        text = NODE.read_text()
        assert 'STUB_CP="$BIGTRANSLATE_HOME/resmgr/lib/*:' in text


class TestEveryNodeIsReached:
    """for_each_remote dropped every node after the first.

    It was "remote_lines | while read ...", which makes the node list the stdin
    of everything in the loop body, and ssh reads stdin unless told not to. The
    first remote's ssh swallowed the rest of the list.

    With one remote there was nothing to swallow, so it went unnoticed for the
    whole life of a two-machine cluster. Adding a third machine exposed it: start
    brought up the second node, reported success, and never mentioned the third
    -- a node silently absent from a run, which is this project's oldest failure
    shape and the reason conf/nodes.conf.example warns about half the throughput
    with no error and no mention.
    """

    def loop(self):
        text = CLUSTER.read_text()
        body = text[text.index("for_each_remote() {"):]
        return body[:body.index("\n}")]

    def test_the_list_is_not_the_loop_body_s_stdin(self):
        # Code only. The comment above the fix quotes the old form on purpose,
        # so a plain substring search matches the explanation as well.
        code = "\n".join(l for l in self.loop().splitlines()
                         if not l.lstrip().startswith("#"))
        assert "remote_lines | while read" not in code, (
            "the first ssh in the loop will swallow every node after it")

    def test_it_reads_from_its_own_descriptor(self):
        loop = self.loop()
        assert "<&3" in loop, (
            "a file on stdin is drained by ssh just as a pipe is; only a "
            "descriptor the body does not inherit survives")
        assert "exec 3<" in loop
        assert "exec 3<&-" in loop, "the descriptor is left open"

    def test_it_stays_posix(self):
        """This script is #!/bin/sh.

        Process substitution passed "bash -n" and failed immediately under sh,
        so the shebang's shell is what validates it.
        """
        assert CLUSTER.read_text().startswith("#!/bin/sh")
        loop = self.loop()
        assert "3< <(" not in loop, "process substitution is not POSIX"

    def test_the_temporary_file_is_removed(self):
        loop = self.loop()
        assert "rm -f" in loop
