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
"""A deployment's own settings should not be edits to a tracked file.

The manager's setenv.sh had drifted thirty six lines from the committed one.
It had gained a block setting the ports and rewriting the service urls, and
lost the POSIX $BASH_SOURCE fix -- invisible on macOS, fatal on a Linux
compute node. Nothing reported it, because a hand edited copy of a tracked
file is not a thing any check was looking for.

The rewritten urls are what made it more than untidy: the second derivation
pointed SOLR_URL at a LAN address Solr does not bind, so the join was three
hours from failing on connection refused with every translation done.
"""
import os
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
CONF = ROOT / "distribution" / "src" / "main" / "resources" / "conf"

# What setenv.sh should end up with, read back from a real shell.
REPORT = ("FILEMGR_PORT WORKFLOW_PORT RESMGR_PORT SOLR_PORT TOMCAT_PORT "
          "BIGTRANSLATE_HOST FILEMGR_URL WORKFLOW_URL RESMGR_URL SOLR_URL")


def env_after_setenv(site=None, shell="bash"):
    """Source setenv.sh in a real shell and read back what it set."""
    home = Path(tempfile.mkdtemp())
    (home / "bin").mkdir()
    (home / "conf").mkdir()
    for name in ("setenv.sh",):
        (home / "bin" / name).write_text(
            (BIN / name).read_text(encoding="utf-8"), encoding="utf-8")
    if site is not None:
        (home / "conf" / "site.sh").write_text(site, encoding="utf-8")
    script = (
        'BIGTRANSLATE_HOME=%s\n. %s/bin/setenv.sh\n'
        'for v in %s; do eval "printf \'%%s=%%s\\n\' $v \\"\\$$v\\""; done\n'
        % (home, home, REPORT))
    out = subprocess.run([shell, "-c", script], capture_output=True,
                         text=True, env={"PATH": os.environ["PATH"]})
    assert out.returncode == 0, out.stderr
    found = {}
    for line in out.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            found[key] = value
    return found


class TestWithoutASiteFile:

    def test_the_defaults_are_unchanged(self):
        env = env_after_setenv()
        assert env["FILEMGR_PORT"] == "9000"
        assert env["SOLR_PORT"] == "8983"
        assert env["FILEMGR_URL"] == "http://localhost:9000"

    def test_a_single_machine_install_stays_on_loopback(self):
        env = env_after_setenv()
        assert env["BIGTRANSLATE_HOST"] == "localhost"
        for name in ("FILEMGR_URL", "WORKFLOW_URL", "RESMGR_URL", "SOLR_URL"):
            assert "localhost" in env[name]


class TestWithASiteFile:

    def test_ports_set_there_win(self):
        env = env_after_setenv(
            "export FILEMGR_PORT=9200\nexport SOLR_PORT=8985\n")
        assert env["FILEMGR_PORT"] == "9200"
        assert env["SOLR_PORT"] == "8985"

    def test_the_urls_follow_the_ports_without_being_restated(self):
        # The whole point: a site file sets ports, and the urls are worked
        # out once. Restating them is what let one of them disagree.
        env = env_after_setenv(
            "export FILEMGR_PORT=9200\nexport WORKFLOW_PORT=9201\n"
            "export RESMGR_PORT=9202\nexport SOLR_PORT=8985\n")
        assert env["FILEMGR_URL"].endswith(":9200")
        assert env["WORKFLOW_URL"].endswith(":9201")
        assert env["RESMGR_URL"].endswith(":9202")
        assert ":8985/solr/bigtranslate" in env["SOLR_URL"]

    def test_the_host_moves_the_manager_urls(self):
        env = env_after_setenv("export BIGTRANSLATE_HOST=10.168.168.6\n")
        for name in ("FILEMGR_URL", "WORKFLOW_URL", "RESMGR_URL"):
            assert "10.168.168.6" in env[name], (
                "a compute node reads these, and localhost is the node")

    def test_solr_stays_on_loopback_even_then(self):
        # Solr binds loopback unless told otherwise, and nothing off this
        # machine reads it. Making it match its neighbours is the edit that
        # left the join three hours from connection refused.
        env = env_after_setenv("export BIGTRANSLATE_HOST=10.168.168.6\n")
        assert "localhost" in env["SOLR_URL"], (
            "SOLR_URL must not follow BIGTRANSLATE_HOST")


class TestItWorksWhereItHasTo:

    def test_a_posix_shell_can_source_it(self):
        # bin/oodt runs under /bin/sh, which is dash on Linux. This file has
        # already been broken that way once, by ${BASH_SOURCE[0]}, and it
        # failed only on the compute nodes.
        env = env_after_setenv("export SOLR_PORT=8985\n", shell="sh")
        assert env["SOLR_PORT"] == "8985"

    def test_a_missing_site_file_is_not_an_error(self):
        env = env_after_setenv(site=None, shell="sh")
        assert env["FILEMGR_PORT"] == "9000"


class TestTheExampleIsUsable:

    def test_it_exists_and_sources_cleanly(self):
        example = CONF / "site.sh.example"
        assert example.exists()
        env = env_after_setenv(example.read_text(encoding="utf-8"))
        # Every line is commented out, so it must change nothing.
        assert env["FILEMGR_PORT"] == "9000"

    def test_it_does_not_teach_people_to_set_the_urls(self):
        text = (CONF / "site.sh.example").read_text(encoding="utf-8")
        for name in ("FILEMGR_URL", "WORKFLOW_URL", "RESMGR_URL", "SOLR_URL"):
            assert "export %s=" % name not in text, (
                "%s in the example invites the second derivation that "
                "caused this" % name)
