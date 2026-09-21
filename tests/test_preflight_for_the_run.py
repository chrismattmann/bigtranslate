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
"""Is the cluster ready to start a run?

Every check here exists because its absence cost a run, and every one of
those failures was silent: the ports answered, the log scrolled, the
document count came out right, and the index was wrong.

bt-cluster preflight asks a different question -- whether the deployment is
consistent across machines -- and this calls it for that part rather than
repeating it.
"""

import os
import subprocess

import pytest

from conftest import BIN

PREFLIGHT = BIN / "bt-preflight"


def home(tmp_path, java="21", corpus_files=3, leftovers=(), db=None,
         solr_docs=None, ports=()):
    h = tmp_path / "home"
    (h / "bin").mkdir(parents=True)
    (h / "conf").mkdir(parents=True)
    for d in ("strings", "translated", "translated-catalog"):
        (h / "data" / d).mkdir(parents=True)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(corpus_files):
        (corpus / ("part-%03d.tsv" % i)).write_text("a\tb\n")
    # A fake java that reports whatever version the test wants, behind the
    # NOTE line the real JVM prints when JDK_JAVA_OPTIONS is set.
    jdk = tmp_path / "jdk" / "bin"
    jdk.mkdir(parents=True)
    (jdk / "java").write_text(
        '#!/bin/sh\n'
        'echo "NOTE: Picked up JDK_JAVA_OPTIONS: -Dsomething=1" >&2\n'
        'echo \'openjdk version "%s.0.1" 2026-01-01\' >&2\n' % java)
    (jdk / "java").chmod(0o755)
    for name in ("strings", "translated", "translated-catalog"):
        if name in leftovers:
            (h / "data" / name / "chunk-00000.json").write_text("{}")
    if db is not None:
        (h / "data" / "translations.sqlite").write_text(db)
    (h / "bin" / "setenv.sh").write_text(
        "BIGTRANSLATE_CORPUS=%s\n"
        "JAVA_HOME=%s\n"
        "export BIGTRANSLATE_CORPUS JAVA_HOME\n" % (corpus, tmp_path / "jdk"))
    # No bt-cluster: the node section is skipped with --local-only anyway.
    return h


def run(h, *args):
    env = dict(os.environ)
    env.update(BIGTRANSLATE_HOME=str(h))
    env.pop("SOLR_URL", None)
    return subprocess.run(
        ["sh", str(PREFLIGHT), "--local-only", "--no-jars", *args],
        capture_output=True, text=True, env=env)


class TestTheJavaVersion:

    def test_java_11_fails_the_check(self, tmp_path):
        # The managers start on 11, the ports answer, and every ingest
        # fails with an NPE hours later. Lucene 10 is class file 65.
        done = run(home(tmp_path, java="11"))
        assert done.returncode == 1
        assert "FAIL" in done.stdout
        assert "11" in done.stdout and "21" in done.stdout

    def test_java_21_passes(self, tmp_path):
        done = run(home(tmp_path, java="21"))
        assert "ok" in done.stdout
        assert "Lucene" not in done.stdout

    def test_the_note_line_does_not_break_the_parse(self, tmp_path):
        # JDK_JAVA_OPTIONS makes the JVM print a NOTE to stderr ahead of the
        # version. Taking the first line parses that and reports a good
        # Java as unreadable.
        done = run(home(tmp_path, java="21"))
        assert "could not read the version" not in done.stdout


class TestLeftoversFromTheLastRun:

    def test_a_populated_data_dir_fails(self, tmp_path):
        # This is the 2026-09-20 failure: chunks present, so the run skips
        # them and indexes the previous run's output as its own.
        done = run(home(tmp_path, leftovers=("translated",)))
        assert done.returncode == 1
        assert "data/translated" in done.stdout
        assert "bt-reset" in done.stdout

    def test_empty_data_dirs_pass(self, tmp_path):
        done = run(home(tmp_path))
        assert "left from a previous run" not in done.stdout


class TestTheTranslationDatabase:

    def test_a_database_older_than_the_chunks_fails(self, tmp_path):
        # The 2026-09-21 failure: the join loads it instead of this run's
        # translations, and reports success.
        h = home(tmp_path, db="previous run")
        chunk = h / "data" / "translated-catalog" / "chunk-00000.json"
        chunk.write_text("{}")
        db = h / "data" / "translations.sqlite"
        os.utime(db, (1, 1))
        done = run(h)
        assert done.returncode == 1
        assert "earlier run" in done.stdout

    def test_no_database_is_the_clean_state(self, tmp_path):
        done = run(home(tmp_path))
        assert "absent" in done.stdout


class TestItIsUsableAsAGate:

    def test_a_clean_cluster_exits_zero(self, tmp_path):
        done = run(home(tmp_path))
        assert done.returncode == 0, done.stdout
        assert "Ready" in done.stdout

    def test_the_verdict_counts_the_problems(self, tmp_path):
        done = run(home(tmp_path, java="11", leftovers=("translated",)))
        assert "problem(s)" in done.stdout
        assert "Not ready to run." in done.stdout

    def test_quiet_prints_only_problems(self, tmp_path):
        done = run(home(tmp_path, java="11"), "--quiet")
        assert "FAIL" in done.stdout
        assert "  ok " not in done.stdout

    def test_a_missing_corpus_fails(self, tmp_path):
        h = home(tmp_path)
        (h / "bin" / "setenv.sh").write_text(
            "BIGTRANSLATE_CORPUS=/nowhere/at/all\n"
            "JAVA_HOME=%s\nexport BIGTRANSLATE_CORPUS JAVA_HOME\n"
            % (tmp_path / "jdk"))
        done = run(h)
        assert done.returncode == 1
        assert "not a directory" in done.stdout

    def test_applefork_sidecars_are_not_counted_as_corpus(self, tmp_path):
        # ._foo.tsv matches *.tsv and once doubled the apparent corpus.
        h = home(tmp_path, corpus_files=3)
        corpus = tmp_path / "corpus"
        for i in range(3):
            (corpus / ("._part-%03d.tsv" % i)).write_text("junk")
        done = run(h)
        assert "3 files" in done.stdout, done.stdout
