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
"""Nothing addresses a service by a port written into the source.

BigTranslate's defaults -- 9000, 9001, 9002, 8080, 8983 -- are the same ones
DRAT and any stock RADiX deployment use. A machine running two of them does
not fail loudly: the second stack's clients reach the first stack's services.
That is not hypothetical. Run against a deployment moved onto its own ports,
the driver script checked a neighbour's ports and reported the services up,
and the translate step posted every document to a neighbour's Solr, where the
core did not exist, the posts 404'd, and 5,968 translations were lost with
nothing said. Gloss reported that neighbour's health as its own.

So: a port may be a default, and it may be read from the environment, but it
may not be the way a component names a service.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "distribution" / "src" / "main" / "resources" / "bin"
GLOSS = REPO / "webapps" / "gloss-services" / "src" / "main" / "java"
WORKFLOW_POLICY = REPO / "workflow" / "src" / "main" / "resources" / "policy"

SHARED_PORTS = ("9000", "9001", "9002", "8080", "8983")


def _addressing_lines(text):
    """Lines that use a shared port to address something, not to default one.

    `FILEMGR_PORT=${FILEMGR_PORT:-9000}` names a default and is fine; the
    environment can still move it. `http://localhost:9000` is an address, and
    is not.
    """
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("*"):
            continue
        for port in SHARED_PORTS:
            if re.search(r"(localhost|127\.0\.0\.1|\$\{OODT_HOST\}):%s\b" % port, line):
                out.append((number, stripped))
                break
            if re.search(r"check_port\s+%s\b" % port, line):
                out.append((number, stripped))
                break
            if re.search(r'portOpen\([^)]*,\s*%s\s*\)' % port, line):
                out.append((number, stripped))
                break
    return out


def test_the_driver_script_does_not_address_services_by_a_written_in_port():
    offenders = _addressing_lines((BIN / "bigtranslate").read_text())
    assert offenders == [], (
        "bin/bigtranslate addresses a service by a written-in port:\n  "
        + "\n  ".join("%d: %s" % o for o in offenders))


def test_the_driver_script_reads_the_deployment_settings():
    text = (BIN / "bigtranslate").read_text()
    assert "setenv.sh" in text, (
        "bin/bigtranslate never reads setenv.sh, so a deployment moved onto "
        "its own ports has a driver script still talking to the defaults")


def test_gloss_does_not_probe_written_in_ports():
    offenders = []
    for java in GLOSS.rglob("*.java"):
        for number, line in _addressing_lines(java.read_text()):
            offenders.append((java.name, number, line))
    assert offenders == [], (
        "Gloss addresses a service by a written-in port:\n  "
        + "\n  ".join("%s:%d: %s" % o for o in offenders))


def test_the_translate_task_posts_where_the_deployment_says():
    text = (WORKFLOW_POLICY / "tasks.xml").read_text()
    assert "[SOLR_URL]" in text, (
        "tasks.xml does not take SolrUrl from the environment")
    assert 'value="http://localhost:8983' not in text, (
        "tasks.xml still posts to a written-in Solr port")


def test_oodt_can_restart():
    """The README has told people to run this for longer than it has existed.

    It fell through to the usage branch, so a configuration change made just
    before it looked as though it had been picked up while the services were
    still running with the old one.
    """
    text = (BIN / "oodt").read_text()
    assert '"$1" = "restart"' in text, "bin/oodt has no restart"


def test_stop_waits_for_the_ports_to_be_free():
    """Returning early is how a stop-then-start leaves nothing running.

    Solr still held its port when the following start ran, which failed with
    "Port ... is already being used" and left the deployment down.
    """
    text = (BIN / "oodt").read_text()
    assert "wait_for_stopped" in text, "bin/oodt does not wait for its ports"
    assert "wait_for_started" in text, "bin/oodt does not wait for its services"


def test_setup_installs_the_translation_service():
    """Without fastapi and uvicorn, `pantogloss serve` is a subcommand that
    exits with "No module named 'uvicorn'" the first time it is used."""
    text = (BIN / "bigtranslate-setup").read_text()
    assert "uvicorn" in text, (
        "bigtranslate-setup installs Pantogloss without its server extra")
