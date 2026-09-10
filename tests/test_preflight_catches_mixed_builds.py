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
"""A deployment assembled from more than one build is a trap.

preflight already checks that each *named* jar is identical across the nine lib
directories. That passes cleanly on a tree built in pieces, and says nothing
about cas-pge being six days older than cas-resource.

That is the drift that hurts. A policy file naming a class added last week,
deployed against a jar built the week before, leaves the condition unable to
instantiate and the stage it gates never released -- and the failure surfaces
hours later as a stage that simply never starts.

Measured on the manager mid-run:

    Sep 10  cas-resource, cas-workflow, oodt-commons
    Sep  4  cas-pge, cas-filemgr, cas-metadata, cas-crawler, cas-cli
"""
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = ROOT / "distribution" / "src" / "main" / "resources" / "bin" / "bt-cluster"

FUNCTIONS = ("bt_jars_from_one_build", "bt_oodt_jars", "bt_file_epoch",
             "bt_file_day")

DAY = 86400


def harness():
    text = CLUSTER.read_text(encoding="utf-8")
    body = []
    for name in FUNCTIONS:
        m = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), text, re.S | re.M)
        assert m, "no shell function named %s" % name
        body.append(m.group(0))
    return "\n".join(body)


def check(tree):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     encoding="utf-8") as h:
        h.write(harness() + '\nbt_jars_from_one_build "$1"\n')
        script = h.name
    out = subprocess.run(["bash", script, str(tree)],
                         capture_output=True, text=True)
    return out.returncode, out.stdout


def tree_with(jars):
    """jars: {name: age_in_days}"""
    home = Path(tempfile.mkdtemp())
    (home / "pge" / "lib").mkdir(parents=True)
    now = time.time()
    for name, age in jars.items():
        f = home / "pge" / "lib" / name
        f.write_bytes(b"PK\x03\x04")
        when = now - age * DAY
        os.utime(f, (when, when))
    return home


class TestOneBuildPasses:

    def test_jars_from_the_same_build_are_fine(self):
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 0,
            "cas-resource-1.11.0.jar": 0,
            "oodt-commons-1.11.0.jar": 0,
        }))
        assert rc == 0, out

    def test_a_few_hours_apart_is_still_one_build(self):
        # A full build takes minutes and can straddle an hour boundary. The
        # drift worth catching is measured in days.
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 0.0,
            "cas-resource-1.11.0.jar": 0.3,
        }))
        assert rc == 0, out

    def test_an_empty_tree_is_not_a_failure(self):
        rc, out = check(Path(tempfile.mkdtemp()))
        assert rc == 0, out


class TestMixedBuildsAreCaught:

    def test_it_fails_and_names_the_split(self):
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 6,
            "cas-filemgr-1.11.0.jar": 6,
            "cas-resource-1.11.0.jar": 0,
        }))
        assert rc != 0, "a six day spread is more than one build"
        assert "cas-pge-1.11.0.jar" in out
        assert "cas-resource-1.11.0.jar" in out
        assert "span" in out

    def test_the_real_case_that_prompted_this(self):
        # cas-pge six days behind cas-resource is exactly the deployment that
        # would have swallowed BT #87's condition class.
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 6,
            "cas-resource-1.11.0.jar": 0,
        }))
        assert rc != 0


class TestItLooksAtTheRightFiles:

    def test_sources_and_javadoc_jars_are_ignored(self):
        # A javadoc jar holds no classes, so treating it as the artifact
        # reads as "class missing" -- which is how I misread this once.
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 0,
            "cas-pge-1.11.0-javadoc.jar": 9,
            "cas-pge-1.11.0-sources.jar": 9,
        }))
        assert rc == 0, "only the artifact jars decide this:\n" + out

    def test_non_oodt_jars_do_not_count(self):
        rc, out = check(tree_with({
            "cas-pge-1.11.0.jar": 0,
            "solr-core-10.0.0.jar": 400,
            "commons-lang3-3.12.jar": 900,
        }))
        assert rc == 0, "third party jars have their own release dates:\n" + out

    def test_the_same_jar_in_many_lib_dirs_counts_once(self):
        # The distribution copies each jar into nine lib directories.
        home = tree_with({"cas-pge-1.11.0.jar": 0})
        for extra in ("workflow", "resmgr", "filemgr"):
            d = home / extra / "lib"
            d.mkdir(parents=True)
            f = d / "cas-pge-1.11.0.jar"
            f.write_bytes(b"PK\x03\x04")
            when = time.time() - 6 * DAY
            os.utime(f, (when, when))
        rc, out = check(home)
        assert rc == 0, (
            "copies of one jar are check 1's job, not this one:\n" + out)


class TestATimestampThatIsNotOne:
    """CI caught what macOS could not.

    GNU stat's -f is --file-system, so the BSD form "stat -f %m file" does not
    simply fail there: it fails on the operand %m and succeeds on the real
    file, printing a filesystem report to stdout before the shell falls
    through to the GNU form. The caller then compares a multi-line blob with
    -lt, which aborts the script under set -e and takes every other preflight
    check down with it:

        bt-cluster: 461: [: Illegal number:   File: "...cas-filemgr.jar"
            ID: 3bf6563c9a3eb2b Namelen: 255  Type: ext2/ext3
            ...
            1789080274

    The helper uses python3 now, which preflight already needs for the policy
    XML. The guard below is for the next helper.
    """

    def test_a_non_numeric_timestamp_is_skipped_not_compared(self):
        text = CLUSTER.read_text(encoding="utf-8")
        assert '*[!0-9]*' in text, (
            "without the guard a malformed timestamp aborts every check")

    def test_the_helpers_do_not_shell_out_to_stat(self):
        text = CLUSTER.read_text(encoding="utf-8")
        for name in ("bt_file_epoch", "bt_file_day"):
            m = re.search(r"^%s\(\) \{.*?^\}" % name, text, re.S | re.M)
            assert "stat " not in m.group(0), (
                "%s uses stat, whose flags mean different things on the "
                "macOS manager and the Linux nodes" % name)

    def test_the_epoch_helper_returns_exactly_one_line(self):
        home = tree_with({"cas-pge-1.11.0.jar": 0})
        jar = home / "pge" / "lib" / "cas-pge-1.11.0.jar"
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                         encoding="utf-8") as h:
            h.write(harness() + '\nbt_file_epoch "$1"\n')
            script = h.name
        out = subprocess.run(["bash", script, str(jar)],
                             capture_output=True, text=True)
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        assert len(lines) == 1, "got %r" % out.stdout
        assert lines[0].isdigit()
