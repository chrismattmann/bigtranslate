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
"""ETLLib went with W1.

tsvtojson, repackage and poster turned every row of every TSV into JSON and
posted it, one task per file. W2 deduplicates globally first and joins the
answers back, and calls none of them. The check for them outlived the
pipeline: a deployment without ETLLib was refused before it could start a
run, for tools nothing would have called.
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution/src/main/resources/bin"
TOOLS = ("tsvtojson", "repackage", "poster")

# The scripts the W2 stages actually run.
STAGES = ("bt-extract-strings", "bt-translate-chunk", "bt-join-index",
          "bt-build-translation-db", "pantogloss-translatejson")


def _code(path):
    """Lines that are not comments, so history can still be written down."""
    return [line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")]


@pytest.mark.parametrize("tool", TOOLS)
def test_a_run_does_not_demand_it(tool):
    assert not [l for l in _code(BIN / "bigtranslate") if tool in l], (
        "bigtranslate still refuses to run without %s" % tool)


@pytest.mark.parametrize("tool", TOOLS)
def test_setup_does_not_claim_to_install_it(tool):
    assert not [l for l in _code(BIN / "bigtranslate-setup") if tool in l], (
        "bigtranslate-setup still reports on %s" % tool)


def test_nothing_is_installed_for_it():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    assert not lines, "requirements.txt still installs: %s" % lines
    assert "etllib" in text.lower(), (
        "the file should say why it is empty, so it does not quietly refill")


@pytest.mark.parametrize("name", STAGES)
def test_the_stages_need_only_the_standard_library(name):
    """What makes the removal safe rather than merely tidy."""
    third_party = set()
    local = {"bt_encoding", "pantogloss_translatejson"}
    tree = ast.parse((BIN / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        for mod in names:
            if mod and mod not in local and mod not in _STDLIB:
                third_party.add(mod)
    assert not third_party, "%s imports %s" % (name, sorted(third_party))


_STDLIB = {
    "argparse", "ast", "collections", "csv", "datetime", "glob", "hashlib",
    "importlib", "io", "json", "os", "pathlib", "re", "shutil", "sqlite3",
    "subprocess", "sys", "tempfile", "time", "unicodedata", "urllib",
}


def test_pantogloss_is_still_checked_for():
    # It is the one thing a translate run does need that is not in the box,
    # and it is not on PyPI, so the message has to say how to get it.
    body = (BIN / "bigtranslate").read_text(encoding="utf-8")
    assert "import pantogloss" in body
    assert "PANTOGLOSS_SOURCE" in body
