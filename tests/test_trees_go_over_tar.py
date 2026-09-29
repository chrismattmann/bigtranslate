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
"""Trees reach a node over tar, not rsync, and lose nothing on the way.

rsync needs to exist on both ends -- "rsync host:dest" runs "rsync --server" on
the node -- and Git for Windows ships 248 POSIX tools without it. Installing
MSYS2's rsync beside it does not rescue the arrangement: measured on paparadelle
on 2026-09-28 with rsync 3.5.1 reachable through --rsync-path,

    rsync to /c/bt-w1/...                  works
    rsync to /Users/mattmann/bt-w1/...     fails, "change_dir failed"
    tar | ssh to /Users/mattmann/bt-w1/... works

The canonical path is an /etc/fstab mapping and the two POSIX runtimes keep
separate mount tables, so MSYS2 tools can see it while rsync launched over ssh
cannot use it. Every machine using the same absolute BIGTRANSLATE_HOME is not a
preference -- the File Manager catalogues absolute paths -- so the transport has
to reach the canonical path.

What these tests protect is the part tar does not give for free: rsync's
--delete, which is why a deployment replaces rather than accumulates.
"""
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
CLUSTER = BIN / "bt-cluster"


def source():
    return CLUSTER.read_text()


class TestNothingCallsRsync:

    def test_no_rsync_is_invoked(self):
        text = source()
        # Comments explain why it is not used, so only real invocations count:
        # a line that runs rsync rather than a line that mentions it.
        calls = [line for line in text.splitlines()
                 if re.search(r"(^|[|;&(]|\s)rsync\s+-", line)
                 and not line.lstrip().startswith("#")]
        assert not calls, "rsync is still invoked: %r" % calls

    def test_the_three_transfers_use_tar(self):
        text = source()
        assert text.count("| $SSH \"$host\"") >= 3, (
            "expected deploy, stage and stage-chunks to each pipe tar over ssh")
        assert "tar -C" in text


class TestTheDeployStillReplacesRatherThanAccumulates:
    """tar has no --delete, and --delete is the half that mattered.

    A deployment that only adds files accumulates them. On the manager that left
    two Mnemosyne versions of the same jar in six classpath directories, and the
    JVM expands lib/* in an order it explicitly does not specify, so which one
    loaded was decided by nothing.
    """

    def deploy_body(self):
        text = source()
        start = text.index("deploy_one() {")
        return text[start:text.index("\ncmd_deploy", start)]

    def test_it_removes_what_it_is_about_to_replace(self):
        body = self.deploy_body()
        assert "rm -rf $replace" in body, (
            "nothing clears the old tree, so stale jars survive a deploy")

    def test_the_replace_list_comes_from_the_node(self):
        """Computed from what is there, not from a list that can go stale."""
        body = self.deploy_body()
        assert "ls -A" in body
        assert "$SSH" in body[:body.index("rm -rf $replace")]

    def test_node_state_is_kept(self):
        body = self.deploy_body()
        for kept in (".venv", "logs", "run", "data"):
            assert "-e %s" % kept in body or "'%s'" % kept in body or kept in body, kept
        # And each is excluded from the removal by name.
        keep_line = next(l for l in body.splitlines() if "grep -vxF" in l)
        for kept in (".venv", "logs", "run", "data"):
            assert kept in keep_line, "%s is not protected from removal" % kept

    def test_the_venv_is_never_copied(self):
        """A virtualenv records absolute paths and is built for one
        architecture; copying one from an arm64 Mac to a Linux box produces a
        tree that looks right and cannot run."""
        assert "--exclude './.venv'" in self.deploy_body()

    def test_job_output_and_logs_survive(self):
        body = self.deploy_body()
        for pattern in ("./logs/*", "./run/*", "./data/jobs/*",
                        "./data/translated/*"):
            assert "--exclude '%s'" % pattern in body, pattern


class TestSetenvIsCopiedLikeAnythingElse:
    """bin/setenv.sh used to be excluded from the copy as per machine.

    It is not per machine. It derives BIGTRANSLATE_HOME from its own location,
    and every per-site value it uses comes from conf/site.sh, which the deploy
    does copy. The manager's and the GPU node's copies were byte identical when
    this was checked.

    Excluding it cost two things. A node that had never been deployed to ended up
    with no setenv.sh at all, because there was nothing to exclude it in favour
    of, and nothing in bin/ runs without sourcing it. And shared logic added to
    it could never reach a node: resolving the virtualenv's program directory
    there left every node still guessing, since its copy was whatever it was
    first seeded with.
    """

    def test_it_is_not_excluded_from_the_deploy(self):
        text = source()
        assert "--exclude './bin/setenv.sh'" not in text, (
            "shared logic added to setenv.sh cannot reach a node while it is "
            "excluded, and a fresh node gets none at all")

    def test_it_is_not_excluded_from_staging_either(self):
        assert "--exclude './setenv.sh'" not in source()

    def test_the_deploy_checks_it_arrived(self):
        """A node without it cannot run anything in bin/, so say so there."""
        text = source()
        assert "bin/setenv.sh did not arrive" in text


class TestTheHashToolIsResolvedNotAssumed:
    """Neither candidate is on all three machines as shipped.

        shasum    stock on macOS and Linux, absent from Git for Windows
        sha1sum   on Linux and Git for Windows, on macOS only through Homebrew

    Both print "<sum>  <path>", so whichever is present works unchanged.
    """

    def test_no_bare_shasum_is_invoked(self):
        for line in source().splitlines():
            if line.lstrip().startswith("#"):
                continue
            assert "-exec shasum" not in line, line.strip()

    def test_both_candidates_are_tried(self):
        text = source()
        assert "command -v sha1sum" in text
        assert "command -v shasum" in text

    def test_each_side_resolves_for_itself(self):
        """What the manager has is not what the node has."""
        text = source()
        assert "BT_SHA1=" in text, "the manager does not resolve one"
        assert "REMOTE_SHA1=" in text, "the node is not asked to resolve one"
        remote = next(l for l in text.splitlines()
                      if l.lstrip().startswith("theirs="))
        assert "$REMOTE_SHA1" in remote


def test_the_script_is_valid_shell():
    done = subprocess.run(["bash", "-n", str(CLUSTER)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


class TestTarSemanticsMatchWhatRsyncDid:
    """The excludes have to mean the same thing under tar as under rsync.

    bsdtar on the manager is what builds the archive, and its --exclude matches
    archive member names, which begin "./". A pattern without that prefix
    silently excludes nothing.
    """

    def test_every_exclude_is_anchored(self):
        body = source()
        patterns = re.findall(r"--exclude '([^']+)'", body)
        assert patterns, "no excludes found at all"
        for p in patterns:
            assert p.startswith("./"), (
                "%r is not anchored to the archive root, so bsdtar matches "
                "nothing and the exclusion silently does not happen" % p)

    def test_the_transport_really_excludes_those_paths(self, tmp_path):
        """Run the actual patterns through tar rather than trusting them."""
        home = tmp_path / "home"
        for d in ("bin", ".venv/lib", "logs", "run", "data/jobs",
                  "data/strings", "filemgr/lib"):
            (home / d).mkdir(parents=True)
        for f in ("bin/setenv.sh", "bin/oodt", ".venv/lib/x", "logs/a.log",
                  "run/a.pid", "data/jobs/j1", "data/strings/chunk-0.json",
                  "filemgr/lib/a.jar"):
            (home / f).write_text("x")

        listing = subprocess.run(
            ["tar", "-C", str(home), "-cf", "-",
             "--exclude", "./.venv", "--exclude", "./logs/*",
             "--exclude", "./run/*", "--exclude", "./data/jobs/*",
             "--exclude", "./data/translated/*",
             "--exclude", "./bin/setenv.sh", "."],
            capture_output=True)
        names = subprocess.run(["tar", "-tf", "-"], input=listing.stdout,
                               capture_output=True).stdout.decode().split()

        for gone in ("./.venv/lib/x", "./logs/a.log", "./run/a.pid",
                     "./data/jobs/j1", "./bin/setenv.sh"):
            assert gone not in names, "%s was copied and should not be" % gone
        for kept in ("./bin/oodt", "./filemgr/lib/a.jar",
                     "./data/strings/chunk-0.json"):
            assert kept in names, "%s was not copied and should be" % kept
