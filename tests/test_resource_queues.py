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


class TestOnlyTranslateLeavesTheMachine:

    def _map(self):
        root = ET.parse(str(RESMGR_POLICY / "node-to-queue-mapping.xml")).getroot()
        out = {}
        for node in root.iter("node"):
            out[node.get("id")] = {q.get("name") for q in node.iter("queue")}
        return out

    def test_every_node_serves_translate(self):
        # A chunk carries no state beyond its own output file, so any node
        # may take any chunk.
        m = self._map()
        assert m, "no nodes mapped"
        for node, queues in m.items():
            assert "translate" in queues, node

    def test_only_the_manager_node_serves_the_managers_queue(self):
        # Extract reads /Volumes/CHIPOTLE_BRICK and join writes
        # /Volumes/BTSOLR. Neither volume exists on a compute node.
        m = self._map()
        serving = [n for n, q in m.items() if "managers" in q]
        assert serving == ["local"], serving

    def test_the_compute_node_cannot_take_extract_or_join(self):
        queues = self._map().get("gpu")
        assert queues is not None, "the gpu node is not mapped"
        assert "managers" not in queues
