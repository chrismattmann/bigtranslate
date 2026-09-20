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
""""The next run starts from nothing" was not true of the logs.

batch-stub.log held five runs across eleven days and 18MB, with nothing
marking where one ended and the next began. bigtranslate.log -- the file
Gloss tails and shows in its pane -- went back further still.

That is a trap rather than untidiness. A run that misbehaves sends you to
these files first, and a stale SEVERE from nine days ago reads exactly like
a live one: same text, same severity, and a timestamp nobody checks because
the file is supposed to be about now. On 2026-09-20 two of them produced a
confident wrong diagnosis of a run that was working correctly -- a
"Cannot evaluate without a [Filename]" from the 11th and a traceback from
the 12th, both reported as the cause of a stall that had already resolved.
"""

import re
import subprocess

from conftest import BIN

RESET = (BIN / "bt-reset").read_text()


def rotation_block():
    """The rotation, lifted out so it can be run against real files."""
    start = RESET.index("stamp=$(date")
    end = RESET.index("\ndone\n", start) + len("\ndone\n")
    return RESET[start:end]


def run_rotation(tmp_path, logs):
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    for name, body in logs.items():
        (tmp_path / "logs" / name).write_text(body)
    out = subprocess.run(
        ["bash", "-c", rotation_block()],
        capture_output=True, text=True,
        env={"BIGTRANSLATE_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    return out, sorted(p.name for p in (tmp_path / "logs").iterdir())


class TestTheLogsAreRotated:

    def test_a_log_with_content_is_moved_aside(self, tmp_path):
        out, names = run_rotation(
            tmp_path, {"batch-stub.log": "a line from a previous run\n"})
        assert "batch-stub.log" not in names, "the stale log is still live"
        assert any(re.fullmatch(r"batch-stub-\d{8}-\d{6}\.log", n)
                   for n in names), names

    def test_the_file_gloss_tails_is_rotated_too(self, tmp_path):
        # bigtranslate.log is what the pane shows. A run that starts with the
        # previous run's tail in it is showing somebody else's output.
        _, names = run_rotation(tmp_path, {"bigtranslate.log": "old output\n"})
        assert "bigtranslate.log" not in names

    def test_content_is_kept_not_deleted(self, tmp_path):
        # The forensics are occasionally worth having, and a reset should not
        # be the thing that destroys them.
        _, names = run_rotation(tmp_path, {"batch-stub.log": "keep me\n"})
        rotated = [n for n in names if n.startswith("batch-stub-")]
        assert (tmp_path / "logs" / rotated[0]).read_text() == "keep me\n"

    def test_an_empty_log_is_left_alone(self, tmp_path):
        # Nothing to preserve and no trap to spring; rotating it would just
        # litter the directory on every reset.
        _, names = run_rotation(tmp_path, {"pantogloss-serve.log": ""})
        assert names == ["pantogloss-serve.log"]

    def test_a_missing_log_is_not_an_error(self, tmp_path):
        out, names = run_rotation(tmp_path, {})
        assert out.returncode == 0
        assert names == []

    def test_all_three_are_covered(self, tmp_path):
        _, names = run_rotation(tmp_path, {
            "batch-stub.log": "x\n",
            "bigtranslate.log": "y\n",
            "pantogloss-serve.log": "z\n"})
        assert not [n for n in names if n.endswith(".log")
                    and "-" not in n.rsplit(".", 1)[0][-16:]], names


class TestTheOperatorIsTold:

    def test_the_warning_mentions_the_logs(self):
        # It lists what it is about to clear, and this is now part of that.
        assert "rotates logs/" in RESET

    def test_rotation_happens_after_the_clearing(self):
        # If it ran first, anything the clearing logged would be lost with
        # the run it belonged to.
        assert RESET.index("Cleared the Solr index") < RESET.index("stamp=$(date")
