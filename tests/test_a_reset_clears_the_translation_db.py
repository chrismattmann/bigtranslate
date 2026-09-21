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
"""The translation database is derived state, and a reset has to clear it.

It was the one derived thing bt-reset did not clear. The join's first step
builds data/translations.sqlite from data/translated-catalog and skips the
work when the database already holds as many chunks as are present -- which
cannot tell this run's 458 chunks from the previous run's 458.

On 2026-09-21 a run that translated all 458 chunks correctly, with zero
skips on either node, went on to load 1,853,614 translations from a
database dated three hours before it started, while 2,286,244 sat unused.
Caught at the join, before the commit; the count is the same 1,853,614 that
the earlier bad run produced, which is what gave it away.

Two defences, matching the two that guard the chunks themselves: the reset
removes it, and the builder refuses one older than its inputs.
"""

import os
import subprocess
import time

import pytest

from conftest import BIN

RESET = BIN / "bt-reset"
BUILD = BIN / "bt-build-translation-db"


def home_with_db(tmp_path):
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    (home / "conf").mkdir(parents=True)
    for d in ("strings", "translated", "translated-catalog", "jobs",
              "winstdb", "run"):
        (home / "data" / d).mkdir(parents=True)
    (home / "filemgr" / "catalog").mkdir(parents=True)
    (home / "data" / "translations.sqlite").write_text("previous run")
    (home / "bin" / "setenv.sh").write_text(
        "FILEMGR_PORT=9\nWORKFLOW_PORT=9\n"
        "SOLR_URL=http://localhost:0/solr\n"
        "export FILEMGR_PORT WORKFLOW_PORT SOLR_URL\n")
    return home


def run_reset(home, *args):
    env = dict(os.environ)
    env.update(BIGTRANSLATE_HOME=str(home))
    return subprocess.run(
        ["sh", str(RESET), "--force", "--keep-solr", "--local-only", *args],
        capture_output=True, text=True, env=env)


class TestTheResetClearsIt:

    def test_the_translation_database_is_removed(self, tmp_path):
        home = home_with_db(tmp_path)
        done = run_reset(home)
        assert done.returncode == 0, done.stderr
        assert not (home / "data" / "translations.sqlite").exists(), \
            "the next run's join would load the previous run's translations"

    def test_a_reset_with_no_database_is_not_an_error(self, tmp_path):
        home = home_with_db(tmp_path)
        (home / "data" / "translations.sqlite").unlink()
        done = run_reset(home)
        assert done.returncode == 0, done.stderr


def chunks(dirpath, n, when=None):
    dirpath.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        p = dirpath / ("chunk-%05d.json" % i)
        p.write_text('{"hola": "hello"}')
        if when is not None:
            os.utime(p, (when, when))


def build(tmp_path, db_age, chunk_age, n=3):
    """A database of `db_age` seconds ago against chunks of `chunk_age`."""
    translated = tmp_path / "translated-catalog"
    now = time.time()
    chunks(translated, n, when=now - chunk_age)
    glossary = tmp_path / "glossary.tsv"
    glossary.write_text("")
    out = tmp_path / "translations.sqlite"
    first = subprocess.run(
        ["python3", str(BUILD), "--translated", str(translated),
         "--glossary", str(glossary), "--out", str(out)],
        capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    os.utime(out, (now - db_age, now - db_age))
    return subprocess.run(
        ["python3", str(BUILD), "--translated", str(translated),
         "--glossary", str(glossary), "--out", str(out)],
        capture_output=True, text=True)


class TestAStaleDatabaseIsRebuilt:

    def test_a_database_older_than_its_chunks_is_rebuilt(self, tmp_path):
        # The 2026-09-21 shape: same chunk count, older database.
        done = build(tmp_path, db_age=10000, chunk_age=10)
        assert done.returncode == 0, done.stdout + done.stderr
        out = done.stdout + done.stderr
        assert "earlier run" in out, out
        assert "leaving it alone" not in out

    def test_a_current_database_is_still_reused(self, tmp_path):
        # Rebuilding every time would add minutes to every join for nothing.
        done = build(tmp_path, db_age=10, chunk_age=10000)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "leaving it alone" in done.stdout + done.stderr

    def test_the_message_names_the_chunk_that_gave_it_away(self, tmp_path):
        done = build(tmp_path, db_age=10000, chunk_age=10)
        assert "chunk-" in done.stdout + done.stderr
