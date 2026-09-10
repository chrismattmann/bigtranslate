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
"""Is what is deployed what we think is deployed?

Two runs in one day were lost to a fix that existed in git and not on disk: a
jar rebuilt and copied into one lib directory out of nine, and a script
committed but never deployed. Both looked identical from the outside, and
neither was visible until hours of compute had been spent.

These cover the manager side, which is what can be checked without a second
machine. A node list holding only the manager has no remotes, so nothing here
reaches for ssh.
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = ROOT / "distribution" / "src" / "main" / "resources" / "bin" / "bt-cluster"

QUEUE_MAP = """<?xml version="1.0" encoding="UTF-8"?>
<cas:nodeMap xmlns:cas="http://oodt.jpl.nasa.gov/1.0/resource">
  <node id="local">
    <queues>
      <queue name="translate"/>
      <queue name="managers"/>
    </queues>
  </node>
</cas:nodeMap>
"""

NODES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<cas:nodes xmlns:cas="http://oodt.jpl.nasa.gov/1.0/resource">
  <node nodeId="local" ip="http://10.0.0.1:2001" capacity="8"/>
</cas:nodes>
"""

CONDITIONS = """<?xml version="1.0" encoding="UTF-8"?>
<cas:conditions xmlns:cas="http://oodt.jpl.nasa.gov/1.0/cas"/>
"""


def tasks_asking_for(*queues):
    body = "".join(
        '<task id="urn:t:%s"><configuration>'
        '<property name="QueueName" value="%s"/>'
        '</configuration></task>' % (q, q) for q in queues)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<cas:tasks xmlns:cas="http://oodt.jpl.nasa.gov/1.0/cas">'
            + body + '</cas:tasks>')


def build_home(tmp_path, jars, tasks=None, queue_map=QUEUE_MAP):
    """A deployment tree with the given jars, as {libdir: contents}."""
    home = tmp_path / "bt-home"
    for d in ("conf", "resmgr/policy", "workflow/policy"):
        (home / d).mkdir(parents=True, exist_ok=True)
    (home / "conf" / "nodes.conf").write_text("local  localhost  8\n")
    (home / "resmgr" / "policy" / "nodes.xml").write_text(NODES_XML)
    (home / "resmgr" / "policy" / "node-to-queue-mapping.xml").write_text(queue_map)
    (home / "workflow" / "policy" / "conditions.xml").write_text(CONDITIONS)
    (home / "workflow" / "policy" / "tasks.xml").write_text(
        tasks if tasks is not None else tasks_asking_for("translate"))
    for libdir, contents in jars.items():
        d = home / libdir
        d.mkdir(parents=True, exist_ok=True)
        (d / "cas-workflow-1.11.0.jar").write_text(contents)
        (d / "cas-resource-1.11.0.jar").write_text("resource")
        (d / "cas-filemgr-1.11.0.jar").write_text("filemgr")
        (d / "bigtranslate-extensions-0.1.jar").write_text("ext")
    return home


def preflight(home):
    return subprocess.run(
        ["sh", str(CLUSTER), "--home", str(home), "preflight"],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})


class TestItCatchesADeploymentThatDisagreesWithItself:

    def test_a_consistent_tree_passes(self, tmp_path):
        home = build_home(tmp_path, {
            "workflow/lib": "same", "resmgr/lib": "same", "pge/lib": "same"})
        done = preflight(home)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "preflight ok" in done.stdout

    def test_a_jar_copied_into_one_lib_dir_is_caught(self, tmp_path):
        # The exact shape of the bug: a jar rebuilt and dropped into the
        # directory being debugged, leaving the other components on the old
        # one. The workflow manager gets the fix; the batch stub does not.
        home = build_home(tmp_path, {
            "workflow/lib": "NEW", "resmgr/lib": "old", "pge/lib": "old"})
        done = preflight(home)
        assert done.returncode != 0
        assert "cas-workflow-*.jar has 2 different versions" in done.stdout
        assert "preflight FAILED" in done.stdout

    def test_a_missing_jar_is_caught(self, tmp_path):
        home = build_home(tmp_path, {"workflow/lib": "same"})
        (home / "workflow" / "lib" / "cas-resource-1.11.0.jar").unlink()
        done = preflight(home)
        assert done.returncode != 0
        assert "cas-resource-*.jar MISSING" in done.stdout

    def test_a_war_carrying_its_own_copy_is_not_a_fault(self, tmp_path):
        # A war is built and deployed on its own schedule and legitimately
        # holds a different copy. Reporting it would be a finding nobody acts
        # on, and a check nobody acts on is a check nobody reads.
        home = build_home(tmp_path, {
            "workflow/lib": "same", "resmgr/lib": "same"})
        webapp = home / "tomcat" / "webapps" / "opsui" / "WEB-INF" / "lib"
        webapp.mkdir(parents=True)
        (webapp / "cas-workflow-1.11.0.jar").write_text("a war's own copy")
        done = preflight(home)
        assert done.returncode == 0, done.stdout
        assert "preflight ok" in done.stdout


class TestItCatchesPolicyThatWillNotLoad:

    def test_unparseable_generated_policy_is_caught(self, tmp_path):
        # A "--" inside an XML comment took the Resource Manager down at
        # startup and the Workflow Manager with it, and the only message
        # naming the cause was several stack traces deep.
        home = build_home(tmp_path, {"workflow/lib": "same"})
        (home / "resmgr" / "policy" / "node-to-queue-mapping.xml").write_text(
            '<?xml version="1.0"?><cas:nodeMap xmlns:cas="urn:x">'
            '<!-- a -- b --></cas:nodeMap>')
        done = preflight(home)
        assert done.returncode != 0
        assert "DOES NOT PARSE" in done.stdout

    def test_missing_policy_is_caught(self, tmp_path):
        home = build_home(tmp_path, {"workflow/lib": "same"})
        (home / "resmgr" / "policy" / "nodes.xml").unlink()
        done = preflight(home)
        assert done.returncode != 0
        assert "nodes.xml MISSING" in done.stdout


class TestItCatchesAQueueNothingServes:

    def test_a_task_asking_for_an_unserved_queue_is_caught(self, tmp_path):
        # Conditions asked for a queue no node served, so the Resource Manager
        # could not schedule them, every condition task failed, and a failed
        # condition reads as a condition that answered no. No condition in the
        # deployment had ever run.
        home = build_home(tmp_path, {"workflow/lib": "same"},
                          tasks=tasks_asking_for("translate", "conditions"))
        done = preflight(home)
        assert done.returncode != 0
        assert "queue [conditions] is asked for but no node serves it" \
            in done.stdout

    def test_queues_that_are_served_pass(self, tmp_path):
        served = QUEUE_MAP.replace(
            '<queue name="managers"/>',
            '<queue name="managers"/><queue name="conditions"/>')
        home = build_home(tmp_path, {"workflow/lib": "same"},
                          tasks=tasks_asking_for("translate", "conditions"),
                          queue_map=served)
        done = preflight(home)
        assert done.returncode == 0, done.stdout
