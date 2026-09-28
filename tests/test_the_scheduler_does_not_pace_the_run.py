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
"""The scheduler's sleep must not be what sets the pace of a run.

Every dispatch in this pipeline goes through the Resource Manager, conditions
included, so the scheduler's cycle is the granularity of the whole thing. At
20 seconds it was not a detail: on the 2026-09-27 corpus run the handover from
extract to translate queued 952 condition jobs against 20 slots on the
conditions node,

    952 jobs / 20 slots = 47.6 batches, x 20 s/cycle = 952 s

and took a measured 17m32s, with every translation slot on both machines idle
throughout. Each of those jobs reads a 7.8KB staging manifest off the local
disk and tests a HashSet.

The cycle is only safe to shorten because the scheduler drains its queue every
cycle instead of dispatching one job per sleep; that was fixed separately, and
this file records the dependency so nobody restores the long sleep to "reduce
load" without checking it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROPS = ROOT / "resmgr" / "src" / "main" / "resources" / "etc" / "resource.properties"
NODES = ROOT / "resmgr" / "src" / "main" / "resources" / "policy" / "nodes.xml"
CLUSTER = (ROOT / "distribution" / "src" / "main" / "resources" / "bin"
           / "bt-cluster")

# Above this, the sleep rather than the work sets how long a stage handover
# takes on a corpus of this size. Chosen with headroom: the measured run needed
# 952 dispatches to get from one stage to the next.
SLOWEST_TOLERABLE_CYCLE_SECONDS = 5


def wait_seconds():
    m = re.search(r"^org\.apache\.oodt\.cas\.resource\.scheduler\.wait\.seconds"
                  r"\s*=\s*(\d+)\s*$", PROPS.read_text(), re.M)
    assert m, "the scheduler cycle is not set at all"
    return int(m.group(1))


def test_the_scheduler_cycle_is_short():
    assert wait_seconds() <= SLOWEST_TOLERABLE_CYCLE_SECONDS, (
        "a %ds cycle paces the run rather than the work: every condition is "
        "dispatched as a job, so this multiplies by the number of chunks"
        % wait_seconds())


def test_the_cycle_is_not_zero():
    """Zero would be a spin, not a schedule."""
    assert wait_seconds() >= 1


def test_the_handover_arithmetic_stays_under_a_minute():
    """The number that matters is cycle x batches, not either alone.

    458 chunks is this corpus at the default chunk size, and the measured run
    needed rather more than one dispatch per chunk before translations began.
    """
    dispatches = 952
    slots = default_conditions_capacity()
    seconds = (dispatches / float(slots)) * wait_seconds()
    assert seconds < 60, (
        "extract to translate would take %.0fs of pure scheduling with %d "
        "slots on a %ds cycle" % (seconds, slots, wait_seconds()))


def default_conditions_capacity():
    """The default bt-cluster writes when nodes.conf names no capacity."""
    m = re.search(r'\$\{conditions:-(\d+)\}', CLUSTER.read_text())
    assert m, "bt-cluster no longer defaults the conditions capacity"
    return int(m.group(1))


def test_the_single_machine_policy_agrees_with_the_generator():
    """Two files ship a conditions capacity and they must not disagree.

    resmgr/policy/nodes.xml is the single-machine default; bt-cluster policy
    overwrites it from conf/nodes.conf on a cluster. A single-machine install
    that is slower than a cluster for no stated reason is the failure here.
    """
    m = re.search(r'nodeId="local-conditions"[^>]*capacity="(\d+)"',
                  NODES.read_text())
    assert m, "the single-machine policy has no conditions node"
    assert int(m.group(1)) == default_conditions_capacity()


def test_conditions_outnumber_translate_slots():
    """Gates are cheap and cached; translations are slow and few."""
    translate = re.search(r'nodeId="local"[^>]*capacity="(\d+)"',
                          NODES.read_text())
    assert translate
    assert default_conditions_capacity() > int(translate.group(1))
