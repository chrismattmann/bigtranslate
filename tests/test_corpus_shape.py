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
"""A directory of TSVs is not the same thing as this corpus.

The files are headerless: the first line is data, and the column names come
positionally from conf/colheaders.txt. The translate columns -- salary,
title, duration and the rest -- are looked up by position and nothing
downstream re-checks that, so a directory of TSVs with different columns
does not fail. It translates whatever sits in those positions and indexes
the result, and the run looks exactly like a good one: products catalogued,
chunks translated, documents posted, no errors anywhere.

Gloss asks for "a TSV directory", which invites precisely that, and a run
is five hours.
"""
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = (ROOT / "distribution" / "src" / "main" / "resources" / "bin"
          / "bigtranslate")
CONF = ROOT / "distribution" / "src" / "main" / "resources" / "conf"


def _function(name):
    """The named shell function, lifted out of the driver verbatim."""
    body, taking = [], False
    for line in DRIVER.read_text().splitlines():
        if line.startswith(name + "() {"):
            taking = True
        if taking:
            body.append(line)
            if line == "}":
                break
    assert body, "no %s() in bigtranslate" % name
    return "\n".join(body)


def run_shape_check(tmp_path, home, corpus):
    script = tmp_path / "probe.sh"
    script.write_text(textwrap.dedent("""\
        set -u
        BIGTRANSLATE_HOME=%s
        %s
        validate_corpus_shape "%s"
        echo ACCEPTED
        """) % (home, _function("validate_corpus_shape"), corpus))
    return subprocess.run(["bash", str(script)], capture_output=True,
                          text=True, timeout=60)


@pytest.fixture
def home(tmp_path):
    """A deployment whose conf says what this corpus looks like."""
    conf = tmp_path / "home" / "conf"
    conf.mkdir(parents=True)
    (conf / "colheaders.txt").write_text(
        "\n".join("col%d" % i for i in range(1, 21)) + "\n")
    (conf / "translate.cols").write_text("salary\ntitle\nduration\n")
    return tmp_path / "home"


def _corpus(where, columns, files=3):
    where.mkdir(parents=True, exist_ok=True)
    for n in range(files):
        row = "\t".join("v%d" % i for i in range(columns))
        (where / ("part-%d.tsv" % n)).write_text(row + "\n" + row + "\n")
    return where


def test_the_right_shape_is_accepted(tmp_path, home):
    corpus = _corpus(tmp_path / "corpus", 20)
    result = run_shape_check(tmp_path, home, corpus)
    assert "ACCEPTED" in result.stdout, result.stdout + result.stderr


def test_a_different_corpus_is_refused(tmp_path, home):
    corpus = _corpus(tmp_path / "other", 3)
    result = run_shape_check(tmp_path, home, corpus)
    assert "ACCEPTED" not in result.stdout
    assert result.returncode != 0


def test_the_refusal_says_what_it_found_and_what_it_wanted(tmp_path, home):
    corpus = _corpus(tmp_path / "other", 7)
    out = run_shape_check(tmp_path, home, corpus).stdout
    assert "has 7 tab separated columns" in out, out
    assert "names 20" in out, out
    # And how to proceed, because a corpus that really does differ is a
    # configuration change rather than a mistake.
    assert "colheaders.txt" in out


def test_nested_files_are_checked_too(tmp_path, home):
    # The crawler recurses, so validation that only looked at the top level
    # would pass a corpus it then read differently.
    root = tmp_path / "nested"
    _corpus(root / "deep" / "deeper", 4)
    result = run_shape_check(tmp_path, home, root)
    assert "ACCEPTED" not in result.stdout


def test_a_deployment_without_a_header_list_is_left_alone(tmp_path):
    # Not the thing that makes a run work, so its absence is not a refusal.
    bare = tmp_path / "bare"
    (bare / "conf").mkdir(parents=True)
    corpus = _corpus(tmp_path / "any", 5)
    result = run_shape_check(tmp_path, bare, corpus)
    assert "ACCEPTED" in result.stdout, result.stdout + result.stderr


def test_the_shipped_header_list_is_what_the_check_reads(tmp_path):
    # If these ever disagree the check is measuring nothing.
    names = [line for line in (CONF / "colheaders.txt").read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert len(names) == 20, "shipped colheaders.txt has %d names" % len(names)


class TestTheCountIsTheCrawlersCount:
    """The only number an operator is given about the size of their run."""

    def test_the_file_count_recurses(self):
        body = _function("validate_corpus_path")
        assert "-maxdepth 1 -type f -name '*.tsv'" not in body, (
            "the count stops at the top level while the crawler recurses; on "
            "the employment corpus that reported 2806 files for a run that "
            "ingested 5616 products")
        assert "find \"$CORPUS_PATH\" -type f -name '*.tsv'" in body
