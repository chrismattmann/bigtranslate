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
"""A service being up is not the same as a task being able to reach it.

The Workflow Manager substitutes the environment's URL into task metadata and
the task connects to it, so what matters is whether that address reaches the
service -- not whether the service is running.

Solr binds loopback unless told otherwise. SOLR_URL had been pointed at the
LAN address, because the compute nodes need reachable URLs for the OODT
managers, which do bind *:port. Solr was up, its core healthy, every page
green, and preflight said ok. The join would have failed on connection
refused three hours into the run with every translation already done.
"""
import re
import socket
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = ROOT / "distribution" / "src" / "main" / "resources" / "bin" / "bt-cluster"


def shell_function(name):
    """Just the one function, so sourcing does not run the whole script."""
    text = CLUSTER.read_text(encoding="utf-8")
    match = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), text,
                      re.S | re.M)
    assert match, "no shell function named %s" % name
    return match.group(0)


def call(name, argument):
    body = shell_function(name)
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(body + '\n%s "$1"\n' % name)
        script = handle.name
    return subprocess.run(["bash", script, argument]).returncode


def a_closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestAnAddressThatDoesNotReachTheService:

    def test_a_url_nothing_answers_is_not_reachable(self):
        url = "http://127.0.0.1:%d/solr/bigtranslate" % a_closed_port()
        assert call("bt_url_reachable", url) != 0, (
            "an address a task cannot connect to must not read as reachable")

    def test_a_url_that_answers_is_reachable(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            assert call("bt_url_reachable",
                        "http://127.0.0.1:%d/solr" % port) == 0
        finally:
            listener.close()

    def test_the_host_in_the_url_is_the_one_dialled(self):
        # The bug exactly: something listening on loopback, a url naming an
        # address it is not bound to. Dialling the port on localhost instead
        # of the url's own host would call this healthy.
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            assert call("bt_url_reachable",
                        "http://192.0.2.1:%d/solr" % port) != 0, (
                "192.0.2.0/24 is reserved and unroutable; if this passes, "
                "the check is dialling the port rather than the address")
        finally:
            listener.close()

    def test_a_url_without_a_host_is_not_a_failure(self):
        # Nothing to check rather than something broken.
        assert call("bt_url_reachable", "not-a-url") == 0


class TestListeningIsDetected:

    def test_a_port_in_use_is_listening(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            assert call("bt_port_listening", str(port)) == 0
        finally:
            listener.close()

    def test_a_free_port_is_not_listening(self):
        assert call("bt_port_listening", str(a_closed_port())) != 0


class TestPreflightUsesIt:

    def test_every_service_url_is_checked(self):
        text = CLUSTER.read_text(encoding="utf-8")
        for name in ("FILEMGR_URL", "WORKFLOW_URL", "RESMGR_URL", "SOLR_URL"):
            assert name in text, "%s is never checked" % name
        assert "bt_url_reachable" in text

    def test_a_stopped_service_is_not_reported_as_misconfigured(self):
        # preflight is run with the stack down too, and "not running" is not
        # a configuration error -- reporting it would train people to ignore
        # the check.
        text = CLUSTER.read_text(encoding="utf-8")
        assert "bt_port_listening" in text, (
            "without the listening guard every url fails when the stack is "
            "down")
