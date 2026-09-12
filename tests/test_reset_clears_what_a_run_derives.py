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
"""A reset has to clear everything a run derives, and the script has to ship.

bt-reset existed only on the manager's own disk for five days. Every reset
between runs went through it, and a deployment made from the repository did
not have it at all -- so the reset that the runs actually depended on was
not in the thing that gets deployed.

What it clears matters as much as that it exists. A run that begins on top
of the last one does not fail; it produces a worse thing than a failure.
Leftover chunk products make the translate stage's lookup return several
comma joined paths and the PGE dies on an argument error that says nothing
about stale catalog entries. Leftover translations make the join's count
reach its target before this run has produced anything, so it indexes the
previous run's work and reports success.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
RESET = BIN / "bt-reset"

# Everything here is rebuilt by a run, and every one of them has to go.
# data/winstdb and data/run are the two the older in-line reset missed:
# instances from the previous run survived, and the run marker left Gloss
# reporting a translation that was not happening.
DERIVED = [
    "data/strings",
    "data/translated",
    "data/translated-catalog",
    "data/jobs",
    "data/winstdb",
    "data/run",
    "filemgr/catalog",
]


def test_the_reset_script_ships():
    assert RESET.is_file(), (
        "bt-reset is not in the distribution, so a deployment made from the "
        "repository cannot reset itself")


def test_it_is_executable():
    assert RESET.stat().st_mode & 0o111, "bt-reset is not executable"


def test_it_clears_everything_a_run_derives():
    body = RESET.read_text()
    missing = [d for d in DERIVED if d not in body]
    assert not missing, "bt-reset never clears: " + ", ".join(missing)


def test_it_does_not_touch_the_corpus():
    body = RESET.read_text()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "BIGTRANSLATE_CORPUS" not in stripped:
            continue
        assert not stripped.startswith("rm "), (
            "a reset must never delete the corpus: " + stripped)


def test_it_refuses_to_run_against_a_live_stack():
    # HSQLDB in file mode is single process and Lucene holds a write lock;
    # clearing either underneath a running manager corrupts rather than
    # resets.
    body = RESET.read_text()
    assert "lsof" in body and "oodt stop" in body, (
        "bt-reset does not check that the stack is stopped")


def test_it_uses_the_shared_schema_tool():
    # bin/oodt runs WorkflowInstanceSchema at startup. A second, separate
    # implementation of the same thing is how the two drift apart.
    body = RESET.read_text()
    assert "WorkflowInstanceSchema" in body, (
        "bt-reset rebuilds the instance schema its own way")


def test_it_exports_oodt_home_for_the_schema_tool():
    # The configured URL is jdbc:hsqldb:file:[OODT_HOME]/data/winstdb/winst.
    # bin/oodt resolves that because bin/env.sh exports OODT_HOME; bt-reset
    # sources only bin/setenv.sh, which does not. Unexported, the placeholder
    # survived, HSQLDB created a directory named "[OODT_HOME]" beside the
    # deployment, and the reset printed "Workflow instance tables created"
    # over an empty data/winstdb.
    body = RESET.read_text()
    call = body.index("WorkflowInstanceSchema")
    before = body[:call]
    assert "export OODT_HOME" in before, (
        "bt-reset runs the schema tool without exporting OODT_HOME, so "
        "[OODT_HOME] in the JDBC URL resolves to nothing")
