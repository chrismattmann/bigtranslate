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
"""The deployment has to know where java is, rather than inherit it.

bin/bt-node launches the batch stub as "$JAVA_HOME/bin/java". Nothing in the
deployment set JAVA_HOME and nothing in the shell profile did either: the stack
had been started from a shell that happened to export it, and the cluster
depended on that shell being the one used next. From any other shell:

    nohup: /bin/java: No such file or directory     <- logs/batch-stub.log
    Batch stub did not reach 2001 within 30s        <- what the operator sees

The diagnosis points at the port. And because the manager's stub starts before
the remotes and bin/bt-cluster runs under set -e, one unset variable on the
manager ended a cluster start before it reached either node -- all three then
reported down, which reads as a network fault.

Which branch of the resolution runs depends on the machine, so the two are
covered on the two platforms this cluster has: /usr/libexec/java_home exists on
the manager and not on a Linux node, where the PATH branch is the one that runs.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
CONF = ROOT / "distribution" / "src" / "main" / "resources" / "conf"

HAS_JAVA_HOME_TOOL = Path("/usr/libexec/java_home").exists()


def a_fake_jdk(root, name="jdk"):
    """A directory with an executable bin/java, which is all the checks ask."""
    home = root / name
    (home / "bin").mkdir(parents=True)
    java = home / "bin" / "java"
    java.write_text('#!/bin/sh\necho fake\n', encoding="utf-8")
    java.chmod(0o755)
    return home


def java_home_after_setenv(site=None, env=None, shell="sh"):
    """Source setenv.sh in a real shell and read back JAVA_HOME."""
    home = Path(tempfile.mkdtemp())
    (home / "bin").mkdir()
    (home / "conf").mkdir()
    (home / "bin" / "setenv.sh").write_text(
        (BIN / "setenv.sh").read_text(encoding="utf-8"), encoding="utf-8")
    if site is not None:
        (home / "conf" / "site.sh").write_text(site, encoding="utf-8")
    script = ('BIGTRANSLATE_HOME=%s\n. %s/bin/setenv.sh >/dev/null 2>&1\n'
              'printf "%%s" "$JAVA_HOME"\n' % (home, home))
    full = {"PATH": os.environ["PATH"]}
    full.update(env or {})
    out = subprocess.run([shell, "-c", script], capture_output=True,
                         text=True, env=full)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


class TestAnExplicitChoiceIsHonoured:
    """The one thing that must not be second-guessed.

    The manager runs its stack under a Homebrew 21 that /usr/libexec/java_home
    does not report, because java_home only lists JVMs installed into
    /Library/Java/JavaVirtualMachines. Discovery there returns 11. If discovery
    overrode the setting, this cluster would silently run its nodes on a
    different JVM from its managers.
    """

    def test_an_exported_java_home_is_left_alone(self, tmp_path):
        jdk = a_fake_jdk(tmp_path)
        found = java_home_after_setenv(env={"JAVA_HOME": str(jdk)})
        assert found == str(jdk)

    def test_conf_site_sh_can_set_it(self, tmp_path):
        jdk = a_fake_jdk(tmp_path)
        found = java_home_after_setenv(site='export JAVA_HOME=%s\n' % jdk)
        assert found == str(jdk), (
            "site.sh is the per-site file and is sourced first; a value set "
            "there has to survive")


class TestDiscovery:

    def test_a_broken_java_home_is_not_passed_through(self, tmp_path):
        """An exported path with no bin/java is a stale setting, not a choice.

        Honouring it reproduces the original failure exactly: bt-node would
        build "$JAVA_HOME/bin/java" out of a directory that has no java in it.
        """
        empty = tmp_path / "not-a-jdk"
        empty.mkdir()
        found = java_home_after_setenv(env={"JAVA_HOME": str(empty)})
        assert found != str(empty), "a JAVA_HOME with no java in it was kept"

    def test_whatever_is_chosen_can_actually_run_java(self, tmp_path):
        """Empty is an acceptable answer; a plausible wrong path is not.

        /usr/bin/java on a Mac with no JDK is a shim, and "two directories up"
        from it is /usr -- a path that passes a careless existence check and is
        not a JVM. So the postcondition is executable, not non-empty.
        """
        found = java_home_after_setenv()
        if found:
            assert os.access(os.path.join(found, "bin", "java"), os.X_OK), (
                "%s was chosen and has no runnable bin/java" % found)

    @pytest.mark.skipif(HAS_JAVA_HOME_TOOL,
                        reason="java_home answers first on macOS")
    def test_java_on_the_path_is_found(self, tmp_path):
        """The branch a Linux node and a Git Bash node both take."""
        jdk = a_fake_jdk(tmp_path)
        path = "%s:%s" % (jdk / "bin", os.environ["PATH"])
        found = java_home_after_setenv(env={"PATH": path, "JAVA_HOME": ""})
        assert found == str(jdk)

    @pytest.mark.skipif(HAS_JAVA_HOME_TOOL,
                        reason="java_home answers first on macOS")
    def test_no_java_anywhere_leaves_it_empty(self, tmp_path):
        bare = tmp_path / "bin"
        bare.mkdir()
        found = java_home_after_setenv(env={"PATH": str(bare), "JAVA_HOME": ""})
        assert found == "", (
            "guessing is worse than an empty value the callers can report")


class TestItSurvivesSetU:
    """setenv.sh is sourced by callers that run set -u.

    The first version of the java block expanded $JAVA_HOME unguarded, which
    ends the caller at that line -- while sourcing, so nothing it would have
    printed gets printed. bin/bt-heartbeat exited 1 with empty stdout and empty
    stderr, which reads as "the heartbeat decided not to beat" rather than as a
    shell error, and six tests failed with no message to go on.
    """

    def test_sourcing_under_set_u_with_nothing_exported(self, tmp_path):
        home = tmp_path / "home"
        (home / "bin").mkdir(parents=True)
        (home / "conf").mkdir(parents=True)
        (home / "bin" / "setenv.sh").write_text(
            (BIN / "setenv.sh").read_text(encoding="utf-8"), encoding="utf-8")
        script = ('set -u\nBIGTRANSLATE_HOME=%s\n. %s/bin/setenv.sh\n'
                  'echo survived\n' % (home, home))
        for shell in ("sh", "bash"):
            out = subprocess.run([shell, "-c", script], capture_output=True,
                                 text=True,
                                 env={"PATH": os.environ["PATH"]})
            assert out.returncode == 0, (
                "%s: %s" % (shell, out.stderr or "died with no message"))
            assert "survived" in out.stdout


class TestTheCallersSayWhatIsWrong:

    def test_bt_node_names_the_variable(self):
        text = (BIN / "bt-node").read_text(encoding="utf-8")
        start = text.index("nohup \"$JAVA_HOME/bin/java\"")
        guard = text[:start]
        assert "JAVA_HOME" in guard.rsplit("\n\n", 1)[-1], (
            "the stub is launched with no check that java exists")
        assert "conf/site.sh" in guard.rsplit("\n\n", 1)[-1], (
            "the message should say where to set it")

    def test_the_example_documents_it(self):
        text = (CONF / "site.sh.example").read_text(encoding="utf-8")
        assert "JAVA_HOME" in text, (
            "a setting nobody knows about is one nobody sets")
