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
"""The SQLite translation cache and its glossary layer.

The cache carries most of the weight in this pipeline: the corpus is daily
snapshots of a live job board, so the same posting recurs across hundreds of
files. On a sample country-day 1,477 field instances collapse to 423 distinct
strings.
"""

import sqlite3

import pytest

from conftest import TranslationCache


@pytest.fixture
def cache(tmp_path):
    c = TranslationCache(str(tmp_path / "cache.sqlite"), "test-model")
    yield c
    c.close()


class TestRoundTrip:
    def test_stores_and_returns_model_output(self, cache):
        cache.put_many({"Tiempo Completo": "Full Time"})
        assert cache.get_many(["Tiempo Completo"]) == {"Tiempo Completo": "Full Time"}

    def test_unknown_sources_are_absent(self, cache):
        assert cache.get_many(["never seen"]) == {}

    def test_empty_query_is_harmless(self, cache):
        assert cache.get_many([]) == {}

    def test_accents_survive_the_round_trip(self, cache):
        cache.put_many({"Prácticas": "Internship"})
        assert cache.get_many(["Prácticas"])["Prácticas"] == "Internship"

    def test_handles_more_sources_than_the_sqlite_variable_limit(self, cache):
        # get_many chunks its IN clause; a split file can carry more distinct
        # strings than SQLite allows host parameters.
        pairs = {"s%d" % i: "t%d" % i for i in range(2500)}
        cache.put_many(pairs)
        assert len(cache.get_many(list(pairs))) == 2500


class TestModelScoping:
    def test_entries_do_not_leak_between_models(self, tmp_path):
        path = str(tmp_path / "cache.sqlite")
        a = TranslationCache(path, "model-a")
        a.put_many({"Inmediato": "from model a"})
        a.close()

        b = TranslationCache(path, "model-b")
        assert b.get_many(["Inmediato"]) == {}
        b.close()

    def test_each_model_keeps_its_own_value(self, tmp_path):
        path = str(tmp_path / "cache.sqlite")
        a = TranslationCache(path, "model-a")
        a.put_many({"x": "a-value"})
        a.close()
        b = TranslationCache(path, "model-b")
        b.put_many({"x": "b-value"})
        b.close()

        a = TranslationCache(path, "model-a")
        assert a.get_many(["x"])["x"] == "a-value"
        a.close()


class TestGlossaryPrecedence:
    def test_seeded_entries_are_readable(self, cache):
        cache.seed_glossary({"Inmediato": "Immediate"})
        assert cache.get_many(["Inmediato"]) == {"Inmediato": "Immediate"}

    def test_seeding_overwrites_wrong_model_output(self, cache):
        # The whole point: correcting the glossary and re-running has to fix
        # values already translated and cached.
        cache.put_many({"Inmediato": "Inmediato"})
        cache.seed_glossary({"Inmediato": "Immediate"})
        assert cache.get_many(["Inmediato"])["Inmediato"] == "Immediate"

    def test_model_output_never_overwrites_a_glossary_entry(self, cache):
        cache.seed_glossary({"Medio Tiempo": "Part Time"})
        cache.put_many({"Medio Tiempo": "Half Time"})
        assert cache.get_many(["Medio Tiempo"])["Medio Tiempo"] == "Part Time"

    def test_origin_is_recorded(self, cache, tmp_path):
        cache.seed_glossary({"a": "A"})
        cache.put_many({"b": "B"})
        rows = dict(cache._conn.execute("SELECT source, origin FROM translation"))
        assert rows == {"a": "glossary", "b": "model"}

    def test_seeding_nothing_is_harmless(self, cache):
        assert cache.seed_glossary({}) == 0

    def test_reseeding_is_idempotent(self, cache):
        cache.seed_glossary({"a": "A"})
        cache.seed_glossary({"a": "A"})
        count = cache._conn.execute("SELECT COUNT(*) FROM translation").fetchone()[0]
        assert count == 1


class TestSchemaMigration:
    def test_adds_the_origin_column_to_an_older_cache(self, tmp_path):
        # Caches written before the glossary existed have no origin column.
        path = str(tmp_path / "old.sqlite")
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE translation ("
            "  model TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL,"
            "  PRIMARY KEY (model, source))"
        )
        conn.execute("INSERT INTO translation VALUES ('test-model', 'x', 'legacy')")
        conn.commit()
        conn.close()

        cache = TranslationCache(path, "test-model")
        try:
            cols = {r[1] for r in cache._conn.execute("PRAGMA table_info(translation)")}
            assert "origin" in cols
            # Pre-existing rows stay readable and default to model origin.
            assert cache.get_many(["x"])["x"] == "legacy"
        finally:
            cache.close()


class TestDisabled:
    def test_a_cacheless_run_is_supported(self):
        cache = TranslationCache(None, "test-model")
        cache.put_many({"a": "A"})
        assert cache.get_many(["a"]) == {}
        assert cache.seed_glossary({"b": "B"}) == 0
        cache.close()
