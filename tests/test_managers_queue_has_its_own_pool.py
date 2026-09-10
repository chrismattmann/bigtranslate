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
"""A queue alone partitions nothing.

The Resource Manager tracks load per node id, so a node's capacity is one pool
shared by every queue that node serves. Giving the managers queue its own name
while leaving it on the translate node's id gave it a name and none of the
capacity that name implies.

On a 458 chunk run the join sat queued behind 131 translate jobs with all eight
of the manager's slots taken -- after every translation it was waiting for had
already succeeded. It was saved by waiting four hours for its chunks rather
than refusing, which is not the same as working.

Conditions were given a second node id on the same host for exactly this
reason. managers was not.
"""
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "distribution" / "src" / "main" / "resources"
CLUSTER = RESOURCES / "bin" / "bt-cluster"


def generate(nodes_conf_text):
    """Run the real generator over a nodes.conf and read what it wrote."""
    home = Path(tempfile.mkdtemp())
    (home / "conf").mkdir()
    (home / "resmgr" / "policy").mkdir(parents=True)
    (home / "conf" / "nodes.conf").write_text(nodes_conf_text, encoding="utf-8")
    env = dict(os.environ, BIGTRANSLATE_HOME=str(home),
               NODES_CONF=str(home / "conf" / "nodes.conf"))
    out = subprocess.run(["bash", str(CLUSTER), "policy"], env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    policy = home / "resmgr" / "policy"
    return (ET.parse(policy / "nodes.xml").getroot(),
            ET.parse(policy / "node-to-queue-mapping.xml").getroot())


def queues_by_node(node_map):
    out = {}
    for node in node_map.iter("node"):
        out[node.get("id")] = {q.get("name") for q in node.iter("queue")}
    return out


def capacities(nodes):
    return {n.get("nodeId"): int(n.get("capacity"))
            for n in nodes.iter("node")}


TWO_NODES = "local  10.0.0.1  8  20  4\ngpu  10.0.0.2  8\n"


class TestEachQueueGetsItsOwnPool:

    def test_managers_is_not_on_the_translate_node_id(self):
        _, node_map = generate(TWO_NODES)
        served = queues_by_node(node_map)
        assert "managers" not in served["local"], (
            "sharing an id with translate means sharing its capacity, which "
            "is how the join queued behind 131 translate jobs")
        assert served["local"] == {"translate"}

    def test_managers_has_a_node_id_of_its_own(self):
        _, node_map = generate(TWO_NODES)
        served = queues_by_node(node_map)
        assert served["local-managers"] == {"managers"}

    def test_conditions_still_has_one_too(self):
        _, node_map = generate(TWO_NODES)
        assert queues_by_node(node_map)["local-conditions"] == {"conditions"}

    def test_the_three_pools_are_separate_ids_on_one_host(self):
        nodes, _ = generate(TWO_NODES)
        ips = {n.get("nodeId"): n.get("ip") for n in nodes.iter("node")}
        assert ips["local"] == ips["local-managers"] == ips["local-conditions"], (
            "they are the same machine; only the accounting is separate")

    def test_capacities_come_from_the_config(self):
        nodes, _ = generate("local  10.0.0.1  8  20  4\n")
        caps = capacities(nodes)
        assert caps["local"] == 8
        assert caps["local-conditions"] == 20
        assert caps["local-managers"] == 4

    def test_managers_capacity_defaults_without_the_field(self):
        # Every existing nodes.conf predates this field.
        nodes, _ = generate("local  10.0.0.1  8\ngpu  10.0.0.2  8\n")
        caps = capacities(nodes)
        assert caps["local-managers"] == 4
        assert caps["local-conditions"] == 20


class TestOnlyTheFirstMachineRunsTheManagers:

    def test_a_compute_node_serves_translate_alone(self):
        _, node_map = generate(TWO_NODES)
        served = queues_by_node(node_map)
        assert served["gpu"] == {"translate"}, (
            "extract reads the corpus and join writes the Solr index, and "
            "those disks are on the manager")
        assert "gpu-managers" not in served
        assert "gpu-conditions" not in served

    def test_a_single_machine_install_still_serves_every_queue(self):
        _, node_map = generate("local  10.0.0.1  8\n")
        served = queues_by_node(node_map)
        every = set().union(*served.values())
        assert every == {"translate", "managers", "conditions"}, (
            "one machine must still be able to run the whole pipeline")


class TestEveryQueueTheTasksAskForIsServed:

    def test_no_task_asks_for_a_queue_no_node_serves(self):
        # An unschedulable job fails as though its work had failed.
        _, node_map = generate(TWO_NODES)
        served = set().union(*queues_by_node(node_map).values())
        policy = ROOT / "workflow" / "src" / "main" / "resources" / "policy"
        wanted = set()
        for name in ("tasks.xml", "conditions.xml"):
            for p in ET.parse(policy / name).getroot().iter("property"):
                if p.get("name") == "QueueName":
                    wanted.add(p.get("value"))
        assert wanted <= served, "unserved queues: %s" % (wanted - served)
