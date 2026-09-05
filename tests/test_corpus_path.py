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
"""The corpus path is checked before anything is started.

A path is pasted, and a pasted path picks things up: a comma from a list, a
stray quote, a "~" that never expanded because it was quoted. DRAT accepted
one of those and reported a running audit over a directory that did not
exist -- catalog cleared, crawl found nothing, and the first sign of trouble
was a zero where a count should have been. Refusing costs a second.
"""
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "distribution" / "src" / "main" / "resources" / "bin" / "bigtranslate"


def run_validation(argument):
    """Call validate_corpus_path on its own, out of the driver script."""
    body = subprocess.run(
        ["sed", "-n", "/^validate_corpus_path() {/,/^}/p", str(DRIVER)],
        capture_output=True, text=True, check=True).stdout
    assert body.strip(), "validate_corpus_path is not in the driver script"
    script = body + '\nvalidate_corpus_path "$1"\necho "RESOLVED=$CORPUS_PATH"\n'
    return subprocess.run(["bash", "-c", script, "bash", argument],
                          capture_output=True, text=True)


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "one.tsv").write_text("a\tb\n")
    (tmp_path / "two.tsv").write_text("c\td\n")
    return tmp_path


def test_a_directory_of_tsv_is_accepted_and_resolved(corpus):
    done = run_validation(str(corpus))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "RESOLVED=" in done.stdout
    assert "2 TSV file(s)" in done.stdout


def test_a_trailing_comma_is_refused(corpus):
    """The one that actually happened."""
    done = run_validation(str(corpus) + ",")
    assert done.returncode != 0
    assert "ends in ','" in done.stdout
    assert "pasted" in done.stdout, "does not say what probably went wrong"


@pytest.mark.parametrize("junk", ['"', "'", ";", "|", "&"])
def test_other_pasted_punctuation_is_refused(corpus, junk):
    done = run_validation(str(corpus) + junk)
    assert done.returncode != 0, "accepted a path ending in %r" % junk


def test_a_path_that_is_not_there_is_refused(tmp_path):
    done = run_validation(str(tmp_path / "nope"))
    assert done.returncode != 0
    assert "nothing at" in done.stdout


def test_a_file_is_refused_with_the_right_advice(corpus):
    done = run_validation(str(corpus / "one.tsv"))
    assert done.returncode != 0
    assert "is a file, not a directory" in done.stdout


def test_an_empty_directory_is_refused(tmp_path):
    """A crawl of nothing finishes instantly and reads exactly like success."""
    done = run_validation(str(tmp_path))
    assert done.returncode != 0
    assert "No .tsv files" in done.stdout


def test_an_unexpanded_tilde_is_refused():
    done = run_validation("~/bigtranslate/input")
    assert done.returncode != 0
    assert "literal ~" in done.stdout


def test_nothing_at_all_is_refused():
    done = run_validation("")
    assert done.returncode != 0
    assert "No path given" in done.stdout


def test_translate_validates_before_it_marks_a_run():
    """Order matters: marking first would leave a marker for a run that never
    started, and Gloss would report it as running for ever."""
    text = DRIVER.read_text()
    validate_at = text.index("validate_corpus_path \"$PRODUCT_PATH\"")
    mark_at = text.index('mark_run "TRANSLATING"')
    assert validate_at < mark_at, (
        "the run is marked before the path is checked")


def test_the_service_runs_as_many_at_once_as_there_are_workers():
    """One at a time is the default, and it is the wrong answer here: eight
    workers sharing one translation queue behind each other, which measured
    slower than loading the model separately in every worker."""
    oodt = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "oodt").read_text()
    assert "--max-concurrency" in oodt
    assert "minPoolSize" in oodt, (
        "concurrency is not derived from the engine's pool size, so the two "
        "can drift apart")


def test_the_device_is_configurable():
    oodt = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "oodt").read_text()
    setenv = (REPO / "distribution" / "src" / "main" / "resources" / "bin" / "setenv.sh").read_text()
    assert "--device" in oodt
    assert "PANTOGLOSS_DEVICE" in setenv
    assert "PANTOGLOSS_DEVICE:-auto}" in setenv, "the default is not auto"
