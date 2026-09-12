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
"""An upgrade must not leave the Resource Manager without its node list.

resmgr/policy/nodes.xml and node-to-queue-mapping.xml are generated from
conf/nodes.conf, and the distribution also ships a stock copy of both.
Unpacking a release over a deployment replaces the generated policy with
the stock one and says nothing about it.

What follows is not a crash. The Resource Manager starts, the Workflow
Manager starts, the run begins -- and every task in a queue no node serves
sits unschedulable for ever. On this deployment the queue is "conditions",
which gates both the translate stage and the join, so the symptom is a run
that crawls, extracts, and then does nothing at all. It reads as slow.

Caught once by bin/bt-cluster preflight, which reported

    manager: queue [conditions] is asked for but no node serves it

but only because preflight happened to be run. The policy is rewritten at
startup now, so the upgrade cannot lose it whether anyone remembers or not.
"""
import subprocess

from conftest import BIN

OODT = BIN / "oodt"
CLUSTER = BIN / "bt-cluster"


def _function(script, name):
    """The named shell function, lifted out of a driver verbatim."""
    body = subprocess.run(
        ["sed", "-n", "/^%s() {/,/^}/p" % name, str(script)],
        capture_output=True, text=True, check=True).stdout
    assert body.strip(), "no %s() in %s" % (name, script.name)
    return body


def test_the_policy_is_written_at_startup():
    assert "ensure_resource_policy" in OODT.read_text(), (
        "nothing rewrites resmgr/policy from conf/nodes.conf at startup; an "
        "upgrade that unpacks over the deployment silently reverts it")


def test_it_runs_before_the_resource_manager_is_launched():
    # The Resource Manager reads its policy once, at startup. Rewriting it
    # afterwards changes a file nothing will read again.
    body = OODT.read_text()
    start = body.index("start_oodt() {")
    call = body.index("ensure_resource_policy", start)
    launch = body.index('"$RESMGR_HOME"/bin/"$RESMGR_EXEC" start', start)
    assert call < launch, (
        "the policy is rewritten after the Resource Manager has read it")


def test_it_goes_through_bt_cluster_rather_than_writing_xml_itself():
    body = _function(OODT, "ensure_resource_policy")
    assert "bt-cluster" in body and "policy" in body, body
    assert "<cas:nodes" not in body, (
        "a second generator of nodes.xml is how the two drift apart")


def test_a_deployment_with_no_node_list_is_left_alone():
    # Single machine deployments never had generated policy and must not be
    # handed an empty one.
    body = _function(OODT, "ensure_resource_policy")
    assert "nodes.conf" in body
    assert "return 0" in body, body


def test_it_does_not_stop_the_start_when_it_fails():
    # A deployment that will not start is worse than one whose policy is
    # stale and says so.
    body = _function(OODT, "ensure_resource_policy")
    assert "||" in body, body
    assert "exit 1" not in body, body


def test_the_generated_files_are_the_ones_the_shipped_policy_overwrites():
    # If bt-cluster ever writes somewhere else, this stops agreeing.
    cluster = CLUSTER.read_text()
    for name in ("resmgr/policy/nodes.xml",
                 "resmgr/policy/node-to-queue-mapping.xml"):
        assert name in cluster, name


# --------------------------------------------------------------------------
# The shipped policy
#
# It is what a fresh install runs on, and it is what an upgrade puts back
# over the generated policy for the moments before bin/oodt rewrites it. It
# was a hand maintained snapshot of a two node cluster, taken before
# conditions were given a node of their own, and it served no "conditions"
# queue at all.

import xml.etree.ElementTree as ET

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POLICY = REPO / "resmgr" / "src" / "main" / "resources" / "policy"
WORKFLOW_POLICY = REPO / "workflow" / "src" / "main" / "resources" / "policy"


def _queues_served():
    root = ET.parse(POLICY / "node-to-queue-mapping.xml").getroot()
    return {q.get("name") for q in root.iter("queue")}


def _queues_wanted():
    wanted = set()
    for name in ("tasks.xml", "conditions.xml"):
        path = WORKFLOW_POLICY / name
        if not path.exists():
            continue
        for element in ET.parse(path).getroot().iter():
            if element.get("name") == "QueueName" and element.get("value"):
                wanted.add(element.get("value"))
    return wanted


def test_the_shipped_policy_parses():
    ET.parse(POLICY / "nodes.xml")
    ET.parse(POLICY / "node-to-queue-mapping.xml")


def test_every_queue_a_task_asks_for_is_served():
    wanted, served = _queues_wanted(), _queues_served()
    assert wanted, "no QueueName in the workflow policy; this test is blind"
    assert wanted <= served, (
        "shipped policy serves %s but tasks ask for %s; the unserved ones "
        "are unschedulable and the run stops without an error"
        % (sorted(served), sorted(wanted)))


def test_every_node_in_the_map_exists_in_nodes_xml():
    declared = {n.get("nodeId")
                for n in ET.parse(POLICY / "nodes.xml").getroot().iter("node")}
    mapped = {n.get("id") for n
              in ET.parse(POLICY / "node-to-queue-mapping.xml").getroot()
              .iter("node")}
    assert mapped <= declared, sorted(mapped - declared)


def test_conditions_do_not_share_a_node_with_translate():
    # One node id is one pool. Sharing it lets long running translations
    # hold every slot while the gates that would end them wait for one.
    root = ET.parse(POLICY / "node-to-queue-mapping.xml").getroot()
    for node in root.iter("node"):
        queues = {q.get("name") for q in node.iter("queue")}
        assert not ({"conditions"} < queues), (
            "node %s serves conditions alongside %s"
            % (node.get("id"), sorted(queues - {"conditions"})))
