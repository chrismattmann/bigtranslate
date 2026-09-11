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
"""The translation database decides what the join can translate.

The join waits for every chunk before indexing. The database it reads was built
before that wait, from whatever had arrived, and the join does not rebuild it.

On a 458 chunk run: database built at 16:16 from 442 chunks, join began at 16:36
with all 458 present. Every document would have been indexed and 155,000 strings
left in Spanish, and the join would have reported success -- the same shape as
the bug #79 fixed, one step upstream.

Reuse made it worse. The builder skipped the build whenever the file existed, so
a stale database survived a re-run that was meant to correct it.
"""
import importlib.machinery
import importlib.util
import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
PGE = (ROOT / "pge" / "src" / "main" / "resources" / "policy" / "no_filter"
       / "PgeConfig_JoinIndex.xml")


def load(name):
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(
            name.replace("-", "_"), str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_chunks(directory, count, start=0):
    directory.mkdir(parents=True, exist_ok=True)
    for n in range(start, start + count):
        name = "chunk-%05d.json" % n
        (directory / name).write_text(
            json.dumps({"origen-%d" % n: "source-%d" % n}), encoding="utf-8")


def rows(db):
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        conn.close()


class TestAStaleDatabaseIsRebuilt:

    def test_a_database_short_of_the_chunks_on_disk_is_rebuilt(self, tmp_path):
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        builder = load("bt-build-translation-db")

        write_chunks(translated, 442)
        assert builder.main(["--translated", translated.as_posix(),
                            "--out", db.as_posix()]) == 0
        assert rows(db) == 442

        # The last chunks arrive, as they did at 16:36.
        write_chunks(translated, 16, start=442)
        assert builder.main(["--translated", translated.as_posix(),
                            "--out", db.as_posix()]) == 0
        assert rows(db) == 458, (
            "a database built before the last chunks arrived must not be "
            "reused; the join indexes every document with a fraction of the "
            "translations and calls it success")

    def test_a_complete_database_is_left_alone(self, tmp_path):
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        builder = load("bt-build-translation-db")
        write_chunks(translated, 20)
        builder.main(["--translated", translated.as_posix(),
                      "--out", db.as_posix()])
        before = db.stat().st_mtime_ns

        builder.main(["--translated", translated.as_posix(),
                      "--out", db.as_posix()])
        assert db.stat().st_mtime_ns == before, (
            "rebuilding a database that already holds every chunk wastes "
            "minutes of a run for nothing")

    def test_a_database_from_before_this_existed_is_rebuilt(self, tmp_path):
        # No record of how many chunks went in: unknown, so not trusted.
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        write_chunks(translated, 5)
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (s TEXT PRIMARY KEY, e TEXT)")
        conn.commit()
        conn.close()

        builder = load("bt-build-translation-db")
        assert builder.main(["--translated", translated.as_posix(),
                            "--out", db.as_posix()]) == 0
        assert rows(db) == 5

    def test_the_chunk_count_is_recorded(self, tmp_path):
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        write_chunks(translated, 7)
        load("bt-build-translation-db").main(
            ["--translated", translated.as_posix(), "--out", db.as_posix()])
        conn = sqlite3.connect(str(db))
        try:
            assert conn.execute("SELECT chunks FROM built").fetchone()[0] == 7
        finally:
            conn.close()


class TestItWaitsForTheChunks:

    def test_it_refuses_rather_than_build_a_short_database(self, tmp_path):
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        write_chunks(translated, 3)
        builder = load("bt-build-translation-db")

        try:
            builder.main(["--translated", translated.as_posix(),
                          "--out", db.as_posix(),
                          "--expect", "10", "--expect-timeout", "1"])
            raise AssertionError("should have refused")
        except SystemExit as e:
            assert "refusing to build" in str(e)
        assert not db.exists(), "nothing half built is left behind"

    def test_it_proceeds_when_every_chunk_is_there(self, tmp_path):
        translated = tmp_path / "translated"
        db = tmp_path / "translations.sqlite"
        write_chunks(translated, 10)
        builder = load("bt-build-translation-db")
        assert builder.main(["--translated", translated.as_posix(),
                            "--out", db.as_posix(),
                            "--expect", "10", "--expect-timeout", "1"]) == 0
        assert rows(db) == 10


class TestThePgeBuildsAfterItKnowsTheCount:

    def _cmds(self):
        root = ET.parse(PGE).getroot()
        return [c.text or "" for c in root.iter("cmd")]

    def test_expected_is_computed_before_the_database_is_built(self):
        cmds = self._cmds()
        expected = next(i for i, c in enumerate(cmds) if "EXPECTED=" in c)
        build = next(i for i, c in enumerate(cmds)
                     if "bt-build-translation-db" in c)
        assert expected < build, (
            "the database was built before the count was even taken, so it "
            "was built from whatever had arrived")

    def test_the_build_waits_for_them(self):
        build = next(c for c in self._cmds() if "bt-build-translation-db" in c)
        assert "--expect $EXPECTED" in build

    def test_the_database_is_built_before_the_join_reads_it(self):
        cmds = self._cmds()
        build = next(i for i, c in enumerate(cmds)
                     if "bt-build-translation-db" in c)
        join = next(i for i, c in enumerate(cmds) if "bt-join-index" in c)
        assert build < join
