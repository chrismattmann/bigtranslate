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
"""What bt-node must not do: report a stub that is not the one serving.

A stop that killed without waiting, and removed the pid file regardless,
left the old stub holding the port. The next start could not bind, exited,
and wrote its own pid down as though it were serving. Jobs went to the old
stub -- older jars, older configuration, stale DNS -- while every restart
and every jar deployed was aimed at a process that had already given up.
Nothing reported anything wrong.
"""

from conftest import BIN

NODE = (BIN / "bt-node").read_text()


class TestStopActuallyStops:

    def test_stop_waits_for_the_port_rather_than_assuming(self):
        assert "wait_for port_free" in NODE

    def test_stop_escalates_when_the_process_ignores_sigterm(self):
        assert "kill -9" in NODE

    def test_stop_finds_the_port_holder_when_there_is_no_pid_file(self):
        # The exact orphan case: file gone, process alive, port held.
        assert "pid=$(stub_pid) || pid=$(port_owner)" in NODE

    def test_stop_keeps_the_pid_file_if_the_port_is_still_held(self):
        # Removing it would tell the next start the port is free.
        assert "still held by pid" in NODE


class TestStartRefusesToLie:

    def test_start_refuses_when_the_port_is_held_without_a_pid_file(self):
        assert "orphaned stub" in NODE

    def test_start_waits_for_the_port_to_be_bound(self):
        assert "wait_for port_taken" in NODE

    def test_start_records_a_pid_only_if_that_pid_holds_the_port(self):
        assert 'holder" != "$started' in NODE
        assert "Refusing to record a pid that is not serving" in NODE


class TestStatusNamesTheDisagreement:

    def test_status_compares_the_pid_file_against_the_port(self):
        assert "port_owner" in NODE and "stub_pid" in NODE

    def test_status_says_where_jobs_are_actually_going(self):
        assert "Jobs are going to" in NODE

    def test_status_fails_when_they_disagree(self):
        # A mismatch must not read as healthy to a script checking exit codes.
        assert NODE.count("exit 1") >= 3
