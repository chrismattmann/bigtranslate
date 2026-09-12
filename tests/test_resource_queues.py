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
"""Which stages may leave the machine, and which may not.

Under the local runner this did not matter: extract and join never reached
the Resource Manager, so a task without a queue was simply run in a local
thread. Under ResourceRunnerFactory every task is submitted, and a task with
no queue of its own is eligible for any node -- including one where the 38GB
corpus and the Solr volume do not exist.
"""

import xml.etree.ElementTree as ET

from conftest import WORKFLOW_POLICY

RESMGR_POLICY = WORKFLOW_POLICY.parent.parent.parent.parent.parent / \
    "resmgr" / "src" / "main" / "resources" / "policy"

W2_TASKS = {
    "urn:bigtranslate:Extract_Strings_Task": "managers",
    "urn:bigtranslate:Translate_Chunk_Task": "translate",
    "urn:bigtranslate:Join_Index_Task": "managers",
}


def _task_properties(task_id):
    root = ET.parse(str(WORKFLOW_POLICY / "tasks.xml")).getroot()
    for task in root.iter("task"):
        if task.get("id") == task_id:
            return {p.get("name"): p.get("value")
                    for p in task.iter("property")}
    raise AssertionError("no task %s" % task_id)


class TestEveryW2TaskHasAQueue:

    def test_each_task_names_its_queue(self):
        for task_id, queue in W2_TASKS.items():
            props = _task_properties(task_id)
            assert props.get("QueueName") == queue, (task_id, props.get("QueueName"))

    def test_each_task_declares_a_load(self):
        # A task the Resource Manager cannot cost cannot be scheduled.
        for task_id in W2_TASKS:
            assert _task_properties(task_id).get("TaskLoad"), task_id


class TestTheShippedPolicyIsASingleMachineDefault:
    """What resmgr/src/main/resources/policy describes.

    It used to be a hand maintained snapshot of the two machine cluster this
    project runs, and it went stale: conditions were given a node id of their
    own and this file was not updated, so it served no "conditions" queue at
    all. An upgrade unpacks it over the generated policy, and until bin/oodt
    rewrote it nothing could schedule a gate.

    It is a single machine default now. The multi node invariants belong to
    the thing that generates the real policy, and are tested against
    bin/bt-cluster policy in test_bt_cluster.py.
    """

    def _map(self):
        root = ET.parse(str(RESMGR_POLICY / "node-to-queue-mapping.xml")).getroot()
        out = {}
        for node in root.iter("node"):
            out[node.get("id")] = {q.get("name") for q in node.iter("queue")}
        return out

    def test_it_describes_one_machine(self):
        addresses = {
            node.get("ip")
            for node in ET.parse(str(RESMGR_POLICY / "nodes.xml")).getroot()
                          .iter("node")
        }
        assert len(addresses) == 1, addresses

    def test_every_queue_the_tasks_ask_for_is_served(self):
        served = set()
        for queues in self._map().values():
            served |= queues
        assert set(W2_TASKS.values()) <= served, sorted(served)
        assert "conditions" in served, (
            "a gate is dispatched as a task; unserved, it never runs and the "
            "run stops without an error")

    def test_managers_and_conditions_each_get_a_node_of_their_own(self):
        # The Resource Manager tracks load per node id, not per queue, so a
        # queue sharing an id shares its capacity. The join once sat queued
        # behind 131 translate jobs on a full node after every translation it
        # was waiting for had already succeeded.
        m = self._map()
        for queue in ("managers", "conditions", "translate"):
            owners = [n for n, q in m.items() if queue in q]
            assert len(owners) == 1, (queue, owners)
            assert m[owners[0]] == {queue}, (owners[0], m[owners[0]])


class TestTheTranslateStageStartsNothing:
    """A stage with nothing downstream must not claim to trigger one.

    TriggerPostIngestWorkflow fires [ProductType]Ingest. For the translate
    stage that is EmploymentTranslatedChunkIngest, which no workflow answers
    to, so sendEvent returned false and every successful translation ended
    with "Action ... returned false" and "Product was not ingested" -- after
    the work was done and catalogued.
    """

    def _pge(self, name):
        return (WORKFLOW_POLICY.parent.parent.parent.parent.parent / "pge" /
                "src" / "main" / "resources" / "policy" / "no_filter" /
                name).read_text()

    def test_translate_has_no_post_ingest_action(self):
        assert "PCS_ActionsIds" not in self._pge("PgeConfig_TranslateChunk.xml")

    def test_extract_keeps_its_post_ingest_action(self):
        # EmploymentStringChunkIngest is what gives each chunk a translate
        # workflow; removing it would stop the pipeline entirely.
        assert "PCS_ActionsIds" in self._pge("PgeConfig_ExtractStrings.xml")

    def test_every_triggered_event_is_declared(self):
        # The rule the missing event broke: a stage that fires
        # [ProductType]Ingest needs that event in events.xml.
        events = (WORKFLOW_POLICY / "events.xml").read_text()
        for pge, product in [("PgeConfig_ExtractStrings.xml",
                              "EmploymentStringChunk")]:
            if "PCS_ActionsIds" in self._pge(pge):
                assert '"%sIngest"' % product in events, product
