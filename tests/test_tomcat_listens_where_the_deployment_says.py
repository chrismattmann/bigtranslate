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
"""Tomcat has to listen where the deployment says.

server.xml ships with Tomcat's defaults and nothing wrote TOMCAT_PORT into it,
so the port was hand edited into the deployed copy and the next unpack quietly
put it back.

That happened on 2026-09-11: a redeploy shipped the default server.xml, Tomcat
came up on 8080 and took 8005 and 8009 with it -- the ImageCat stack's ports on
that machine -- and the File Manager failed alongside it. Two stacks on one port
do not fail loudly, which is the whole reason this deployment moves its ports in
the first place.

The same shape as setenv.sh before #86: a per-deployment setting living in a
file the distribution overwrites.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OODT = ROOT / "distribution" / "src" / "main" / "resources" / "bin" / "oodt"

DEFAULT_SERVER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Server port="8005" shutdown="SHUTDOWN">
  <Service name="Catalina">
    <Connector port="8080" protocol="HTTP/1.1"
               connectionTimeout="20000"
               redirectPort="8443" />
    <Connector port="8009" protocol="AJP/1.3" redirectPort="8443" />
  </Service>
</Server>
"""


def run_ensure(server_xml, tomcat_port, extra_env=None):
    """Run the real ensure_tomcat_ports against a throwaway tomcat tree."""
    base = Path(tempfile.mkdtemp())
    (base / "tomcat" / "conf").mkdir(parents=True)
    xml = base / "tomcat" / "conf" / "server.xml"
    xml.write_text(server_xml, encoding="utf-8")

    text = OODT.read_text(encoding="utf-8")
    match = re.search(r"^ensure_tomcat_ports\(\) \{.*?^\}", text, re.S | re.M)
    assert match, "no ensure_tomcat_ports in bin/oodt"

    script = base / "run.sh"
    script.write_text(
        "OODT_BASE=%s\nTOMCAT_PORT=%s\n%s\nensure_tomcat_ports\n"
        % (base, tomcat_port, match.group(0)), encoding="utf-8")
    env = dict(os.environ)
    env.update(extra_env or {})
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                         env=env)
    assert out.returncode == 0, out.stdout + out.stderr
    return xml.read_text(encoding="utf-8")


def ports(xml):
    return {
        "shutdown": re.search(r'<Server\s+port="(\d+)"', xml).group(1),
        "http": re.search(r'<Connector\s+port="(\d+)"\s+protocol="HTTP/1\.1"',
                          xml).group(1),
        "ajp": re.search(r'<Connector\s+port="(\d+)"\s+protocol="AJP/1\.3"',
                         xml).group(1),
    }


class TestThePortsFollowTheDeployment:

    def test_a_default_server_xml_is_moved_off_8080(self):
        got = ports(run_ensure(DEFAULT_SERVER_XML, "8280"))
        assert got["http"] == "8280", (
            "the shipped default is 8080, which on this machine belongs to "
            "another stack")

    def test_shutdown_and_ajp_move_too(self):
        # Leaving these at 8005 and 8009 takes the other stack's ports even
        # when the HTTP port is right, which is exactly what happened.
        got = ports(run_ensure(DEFAULT_SERVER_XML, "8280"))
        assert got["shutdown"] == "8205"
        assert got["ajp"] == "8209"

    def test_the_offsets_are_tomcats_own(self):
        # 8080/8005/8009 -> keep the same relationship at any base port.
        got = ports(run_ensure(DEFAULT_SERVER_XML, "9080"))
        assert (got["http"], got["shutdown"], got["ajp"]) == ("9080", "9005", "9009")

    def test_either_can_be_overridden(self):
        got = ports(run_ensure(DEFAULT_SERVER_XML, "8280", {
            "TOMCAT_SHUTDOWN_PORT": "8999", "TOMCAT_AJP_PORT": "8998"}))
        assert got["shutdown"] == "8999"
        assert got["ajp"] == "8998"


class TestItConverges:

    def test_running_it_twice_is_the_same_as_once(self):
        once = run_ensure(DEFAULT_SERVER_XML, "8280")
        twice = run_ensure(once, "8280")
        assert once == twice

    def test_an_already_edited_file_is_rewritten_not_left(self):
        # A deployment whose port was set by hand to something else must still
        # end up where the settings say, or the two disagree silently.
        edited = DEFAULT_SERVER_XML.replace('port="8080"', 'port="7777"')
        got = ports(run_ensure(edited, "8280"))
        assert got["http"] == "8280"

    def test_a_missing_server_xml_is_not_an_error(self):
        base = Path(tempfile.mkdtemp())
        text = OODT.read_text(encoding="utf-8")
        body = re.search(r"^ensure_tomcat_ports\(\) \{.*?^\}", text,
                         re.S | re.M).group(0)
        script = base / "run.sh"
        script.write_text("OODT_BASE=%s\nTOMCAT_PORT=8280\n%s\nensure_tomcat_ports\n"
                          % (base, body), encoding="utf-8")
        out = subprocess.run(["bash", str(script)], capture_output=True, text=True)
        assert out.returncode == 0


class TestItIsActuallyCalled:

    def test_start_and_stop_both_call_it(self):
        text = OODT.read_text(encoding="utf-8")
        # stop talks to the shutdown port, so it has to agree with start or a
        # stop silently fails and the next start finds the port taken.
        assert text.count("ensure_tomcat_ports") >= 3, (
            "expected the definition plus a call on start and on stop")
