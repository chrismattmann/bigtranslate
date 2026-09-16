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
"""The distribution ships the instance repository its own tooling assumes.

bin/oodt builds the JDBC tables at startup, bt-reset rebuilds them after
clearing, and the schema ships alongside. Only workflow.properties said
Lucene, so every deployment had to be hand edited into agreement with itself
-- and a hand edit to a tracked file is exactly what goes missing on the next
deploy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROPS = ROOT / "workflow/src/main/resources/etc/workflow.properties"
POM = ROOT / "pom.xml"
OODT = ROOT / "distribution/src/main/resources/bin/oodt"
RESET = ROOT / "distribution/src/main/resources/bin/bt-reset"

FACTORY = "org.apache.oodt.cas.workflow.instrepo.DataSourceWorkflowInstanceRepositoryFactory"


def _live(path):
    return [l for l in path.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def test_the_jdbc_repository_is_the_one_configured():
    active = [l for l in _live(PROPS) if "instanceRep.factory" in l]
    assert len(active) == 1, active
    assert active[0].endswith(FACTORY), active[0]


def test_its_connection_settings_are_not_commented_out():
    keys = ("datasource.jdbc.url", "datasource.jdbc.user",
            "datasource.jdbc.driver")
    for key in keys:
        assert [l for l in _live(PROPS) if key in l], "%s is not set" % key


def test_the_url_points_inside_the_deployment():
    url = [l for l in _live(PROPS) if "datasource.jdbc.url" in l][0]
    assert "[OODT_HOME]" in url, (
        "an absolute path here follows the tarball onto every machine")
    assert "hsqldb:file:" in url


def test_the_schema_comes_from_mnemosyne():
    # The repository needs its tables and does not make them. The schema used
    # to be a file here, copied from Mnemosyne and drifting from it -- this
    # copy had lost the waiting_on column. It now lives in cas-workflow, and
    # WorkflowInstanceSchema applies the copy bundled in that jar when no .sql
    # is named.
    assert not (ROOT / "workflow/src/main/resources/etc/workflow-instances.sql").exists(), (
        "the schema is back as a local file; it belongs to cas-workflow")
    import re as _re
    version = _re.search(r"<oodt\.version>([^<]+)</oodt\.version>", POM.read_text()).group(1)
    # The bundled-schema fallback first ships in 1.13.1. Against anything
    # older, calling the tool without a path is an error rather than a default.
    assert tuple(int(p) for p in version.split(".")) >= (1, 13, 1), (
        "oodt.version is %s; the bundled schema fallback needs 1.13.1" % version)


def test_the_tool_is_not_handed_a_schema_path():
    # Passing one would override the bundled schema with a file that no longer
    # exists, which is how this would fail at deployment start rather than here.
    for script in (OODT, RESET):
        body = script.read_text()
        call = body.index("WorkflowInstanceSchema")
        tail = body[call:call + 200]
        assert ".sql" not in tail, (
            "%s still passes a schema path to the tool" % script.name)


def test_startup_builds_the_tables():
    body = OODT.read_text()
    assert "WorkflowInstanceSchema" in body
    # The promoted class, not a copy of it in this repository.
    assert "org.apache.oodt.cas.workflow.instrepo.WorkflowInstanceSchema" in body


def test_a_reset_rebuilds_them():
    body = RESET.read_text()
    assert "WorkflowInstanceSchema" in body
    assert "org.apache.oodt.cas.workflow.instrepo.WorkflowInstanceSchema" in body


def test_lucene_is_not_still_selected():
    active = [l for l in _live(PROPS) if "instanceRep.factory" in l]
    assert not [l for l in active if "Lucene" in l]
