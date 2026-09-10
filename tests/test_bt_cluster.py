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
"""Running on more than one machine, without editing anything per machine.

The first two-node run was assembled by hand: a node block appended to one
machine's setenv.sh, jars copied into fourteen lib directories, chunks
rsynced, an NFS mount that hung twice. None of it was written anywhere a
second run could repeat, and every address in it named one of two specific
machines.
"""

import os
import subprocess
import xml.etree.ElementTree as ET

import pytest

from conftest import BIN, CONF

CLUSTER = BIN / "bt-cluster"


def run(tmp_path, *args, nodes="local  localhost  8\n"):
    home = tmp_path / "bt-home"
    (home / "conf").mkdir(parents=True, exist_ok=True)
    (home / "resmgr" / "policy").mkdir(parents=True, exist_ok=True)
    (home / "conf" / "nodes.conf").write_text(nodes)
    return subprocess.run(
        ["sh", str(CLUSTER), "--home", str(home), *args],
        capture_output=True, text=True, env={"PATH": os.environ["PATH"],
                                             "HOME": os.environ["HOME"]}), home


class TestItNeedsNoEnvironment:

    def test_home_can_be_given_on_the_command_line(self, tmp_path):
        # Driving it from somewhere that has not sourced setenv.sh.
        done, _ = run(tmp_path, "nodes")
        assert done.returncode == 0, done.stderr
        assert "local" in done.stdout

    def test_a_missing_node_list_is_reported_not_ignored(self, tmp_path):
        home = tmp_path / "empty"
        (home / "conf").mkdir(parents=True)
        done = subprocess.run(["sh", str(CLUSTER), "--home", str(home), "nodes"],
                              capture_output=True, text=True)
        assert done.returncode != 0
        assert "no node list" in done.stderr


class TestPolicyIsGeneratedFromTheNodeList:

    THREE = ("manager  10.0.0.1  8\n"
             "gpu      10.0.0.2  8\n"
             "spare    10.0.0.3  4\n")

    def test_every_node_reaches_nodes_xml(self, tmp_path):
        # Two nodes used to be hardcoded, through BIGTRANSLATE_NODE_URL and
        # BIGTRANSLATE_NODE2_URL. A third meant inventing a third variable.
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        assert done.returncode == 0, done.stderr
        root = ET.parse(home / "resmgr" / "policy" / "nodes.xml").getroot()
        ids = [n.get("nodeId") for n in root.iter("node")]
        # The manager appears three times: translate, managers, conditions.
        # The Resource Manager tracks load per node id rather than per queue,
        # so an id is a pool -- three ids on one host is what keeps long
        # running translations from exhausting the slots the other two need.
        assert ids == ["manager", "manager-managers", "manager-conditions",
                       "gpu", "spare"]

    def test_capacity_carries_through(self, tmp_path):
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        root = ET.parse(home / "resmgr" / "policy" / "nodes.xml").getroot()
        caps = {n.get("nodeId"): n.get("capacity") for n in root.iter("node")}
        assert caps == {
            "manager": "8",
            "manager-managers": "4",
            "manager-conditions": "20",
            "gpu": "8",
            "spare": "4"
        }

    def test_addresses_are_not_loopback(self, tmp_path):
        # localhost is correct on the machine that writes it and meaningless
        # on the machine that reads it.
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        text = (home / "resmgr" / "policy" / "nodes.xml").read_text()
        assert "localhost" not in text

    def _serving(self, tmp_path):
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        root = ET.parse(
            home / "resmgr" / "policy" / "node-to-queue-mapping.xml").getroot()
        return {
            node.get("id"): {q.get("name") for q in node.iter("queue")}
            for node in root.iter("node")
        }

    def test_only_the_manager_serves_the_managers_queue(self, tmp_path):
        # Extract reads the corpus and join writes the Solr index; those
        # disks are attached to the machine running the managers.
        serving = self._serving(tmp_path)
        # On the manager machine, but under an id of its own: sharing the
        # translate id would share its capacity, and the join once sat queued
        # behind 131 translate jobs on a full node with every translation it
        # was waiting for already done.
        assert serving["manager-managers"] == {"managers"}
        assert serving["manager"] == {"translate"}
        assert serving["gpu"] == {"translate"}
        assert serving["spare"] == {"translate"}
        assert "gpu-managers" not in serving
        assert "spare-managers" not in serving

    def test_conditions_get_a_pool_translations_cannot_exhaust(self, tmp_path):
        # The Resource Manager tracks load per node id, not per queue, so one
        # id is one pool shared by every queue that node serves. A queue alone
        # partitions nothing: a few long running translations hold every slot
        # and the conditions gating the rest of the run cannot get one, so the
        # gates never open. A second id on the same host is what separates
        # them.
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        root = ET.parse(home / "resmgr" / "policy" / "nodes.xml").getroot()
        nodes = {n.get("nodeId"): n for n in root.iter("node")}

        assert "manager-conditions" in nodes
        assert nodes["manager-conditions"].get("ip") == nodes["manager"].get("ip"), (
            "the conditions pool is the same machine, reached the same way")
        assert nodes["manager-conditions"].get("capacity") == "20"

        serving = self._serving(tmp_path)
        assert serving["manager-conditions"] == {"conditions"}
        assert "conditions" not in serving["manager"], (
            "sharing the manager's pool is the thing this exists to stop")

    def test_the_conditions_pool_is_sizeable_from_nodes_conf(self, tmp_path):
        done, home = run(
            tmp_path, "policy",
            nodes="manager 10.0.0.1 8 40\ngpu 10.0.0.2 8\n")
        root = ET.parse(home / "resmgr" / "policy" / "nodes.xml").getroot()
        nodes = {n.get("nodeId"): n.get("capacity") for n in root.iter("node")}
        assert nodes["manager"] == "8"
        assert nodes["manager-conditions"] == "40"

    def test_only_the_manager_gets_a_conditions_pool(self, tmp_path):
        # A condition is dispatched as a task, and a task with no queue lands
        # on ResourceRunner's default of "high", which nothing here serves.
        # The Resource Manager cannot schedule it, the condition task fails,
        # and a failed condition task is read as a condition that said no --
        # so before this queue existed, no condition in this cluster had ever
        # run.
        #
        # Its own queue rather than sharing managers: a condition is re-asked
        # until it passes, and a few hundred gated tasks would otherwise crowd
        # extract and join out of the queue they need.
        serving = self._serving(tmp_path)
        for node in ("gpu", "spare"):
            assert "conditions" not in serving[node], (
                "a condition reads the manager's own files, so a compute node "
                "must not be offered one")
            assert node + "-conditions" not in serving, (
                "only the manager needs a second pool")

    def test_generated_files_say_they_are_generated(self, tmp_path):
        done, home = run(tmp_path, "policy", nodes=self.THREE)
        for f in ("nodes.xml", "node-to-queue-mapping.xml"):
            assert "bt-cluster" in (home / "resmgr" / "policy" / f).read_text()


class TestNodeSelection:

    TWO = "manager  10.0.0.1  8\ngpu  10.0.0.2  8\n"

    def test_an_unknown_node_is_an_error(self, tmp_path):
        done, _ = run(tmp_path, "stage", "nosuch", nodes=self.TWO)
        assert done.returncode != 0
        assert "no node called" in done.stderr


class TestTheShippedConfig:

    def test_a_node_list_ships(self):
        assert (CONF / "nodes.conf").exists()

    def test_it_documents_the_path_rule(self):
        # The rule that is not obvious and cost the most time.
        text = (CONF / "nodes.conf").read_text()
        assert "absolute path" in text.lower() or "same" in text.lower()
