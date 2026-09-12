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
        """) % (home, _function("corpus_files") + "\n"
                + _function("validate_corpus_shape"), corpus))
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
    """The only number an operator is given about the size of their run.

    It has been wrong in both directions. Counted with -maxdepth 1 it said
    2,806 for a crawl that ingested 5,616 products. Counted recursively with
    no filter it said 5,612, of which 2,806 were AppleDouble forks. Both the
    count and the crawl now go through the same definition of what a corpus
    file is, so the two cannot disagree again.
    """

    def test_the_file_count_recurses(self):
        body = _function("corpus_files")
        assert "-maxdepth 1" not in body, (
            "the count stops at the top level while the crawler recurses; on "
            "the employment corpus that reported 2806 files for a run that "
            "ingested 5616 products")
        assert "-type f -name '*.tsv'" in body

    def test_the_count_goes_through_corpus_files(self):
        body = _function("validate_corpus_path")
        assert "corpus_files" in body, (
            "the count has its own find again; it and the crawl will drift")
        assert "find \"$CORPUS_PATH\" -type f -name '*.tsv'" not in body

    def test_corpus_files_skips_dot_directories(self):
        assert "/\\." in _function("corpus_files")

    def test_the_crawl_excludes_what_the_count_excludes(self):
        driver = DRIVER.read_text()
        assert "corpus_exclude_pattern" in driver
        # Set whether or not the operator passed --exclude. An operator who
        # has never heard of AppleDouble cannot be expected to ask for it.
        start = driver.index("function translate {")
        body = driver[start:driver.index("\n}", start)]
        assert "corpus_exclude_pattern" in body
        # Both branches of the argument parsing -- with --exclude and
        # without -- set it, and neither sets it empty. It is cleared once
        # afterwards, deliberately, so the crawl's exclude does not leak
        # into the stages that follow; that one is not in this slice.
        decided = body[:body.index("say \"Crawling")]
        settings = [line.strip() for line in decided.splitlines()
                    if "BIGTRANSLATE_EXCLUDE=" in line]
        assert len(settings) == 2, settings
        assert not any(line.endswith('BIGTRANSLATE_EXCLUDE=""')
                       for line in settings), (
            "an empty exclude lets the crawler back into .AppleDouble")


# --------------------------------------------------------------------------
# AppleDouble sidecars
#
# The corpus volume has been served over AFP, so beside every file there is a
# 741 byte resource fork under .AppleDouble/ carrying the same name -- it ends
# in .tsv and matches -name '*.tsv' exactly as the real file does. 2,806 real
# files, 2,806 sidecars.
#
# Two things went wrong because nothing excluded them. The crawler ingested
# all 5,616 as products. And the shape check sampled one, found no tabs in a
# binary fork, and refused the run naming "computrabajo-ar-20121106.tsv" --
# the basename of the sidecar, which is also the basename of a real file that
# was perfectly fine. Whether it sampled the sidecar or the real file came
# down to the order find happened to return them in, which is not stable.

def _sidecars(corpus):
    """An AppleDouble fork for every file, as the real volume has."""
    hidden = corpus / ".AppleDouble"
    hidden.mkdir(parents=True, exist_ok=True)
    for real in sorted(corpus.glob("*.tsv")):
        (hidden / real.name).write_bytes(b"\x00\x05\x16\x07\x00\x02" + b"\x00" * 80)
    return hidden


def test_appledouble_sidecars_do_not_fail_a_good_corpus(tmp_path, home):
    corpus = _corpus(tmp_path / "corpus", 20)
    _sidecars(corpus)
    result = run_shape_check(tmp_path, home, corpus)
    assert "ACCEPTED" in result.stdout, result.stdout + result.stderr


def test_a_dot_directory_is_not_corpus(tmp_path, home):
    corpus = _corpus(tmp_path / "corpus", 20)
    _corpus(corpus / ".lacie", 3)
    result = run_shape_check(tmp_path, home, corpus)
    assert "ACCEPTED" in result.stdout, result.stdout + result.stderr


def test_the_refusal_names_a_path_not_a_basename(tmp_path, home):
    # Two files with the same name, one good and one not. The message has to
    # say which one it read.
    corpus = _corpus(tmp_path / "corpus", 20)
    nested = corpus / "sub"
    nested.mkdir()
    (nested / "part-0.tsv").write_text("only\tthree\tcolumns\n")
    result = run_shape_check(tmp_path, home, corpus)
    assert result.returncode != 0
    assert "sub/part-0.tsv" in result.stdout, result.stdout


def test_the_refusal_does_not_dump_the_comments_in_translate_cols(tmp_path, home):
    # translate.cols is mostly a long comment explaining why department is
    # absent. Pasted in whole it filled the screen and buried the columns.
    (home / "conf" / "translate.cols").write_text(
        "# a comment that must not appear\n#\n# nor this one\nsalary\ntitle\n")
    corpus = _corpus(tmp_path / "other", 7)
    result = run_shape_check(tmp_path, home, corpus)
    assert result.returncode != 0
    assert "a comment that must not appear" not in result.stdout, result.stdout
    assert "salary title" in result.stdout, result.stdout
