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
"""Gloss reports how many strings the last run translated.

It read W1's per-file cache, which is written only when a PGE is given
--cache and which nothing under W2 creates. So it answered nought after a
run that had translated 2,286,371 strings, and nought is exactly what an
empty corpus looks like: it read as a broken pipeline rather than as a panel
pointed at a file that is never written.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "webapps/gloss-services/src/main/java/org/bigtranslate/gloss"
CONSTANTS = SERVICES / "FileConstants.java"
REST = SERVICES / "rest/ServicesRestResource.java"
SUMMARY = (ROOT / "webapps/gloss/src/main/webapp/resources/src/components"
           / "SummaryBar.vue")
BUILDER = ROOT / "distribution/src/main/resources/bin/bt-build-translation-db"
JOIN = ROOT / "distribution/src/main/resources/bin/bt-join-index"


def test_the_w1_cache_is_no_longer_read():
    # The path, not the word: the comment explaining why it moved mentions
    # the old location on purpose, and that is worth keeping.
    code = [line for line in CONSTANTS.read_text().splitlines()
            if not line.lstrip().startswith(("*", "/*", "//"))]
    assert not [line for line in code if "translationcache" in line], (
        "still pointed at W1's cache, which no W2 run writes")


def test_it_reads_the_database_the_join_builds():
    assert "data/translations.sqlite" in CONSTANTS.read_text()
    assert "translationsDb()" in REST.read_text()


def test_the_table_is_the_one_that_is_there():
    # The builder writes table t; the old code counted a table called
    # translation, which does not exist in this database.
    rest = REST.read_text()
    assert "SELECT COUNT(*) FROM t" in rest
    assert "FROM translation" not in rest


def test_the_name_matches_what_the_builder_writes():
    # If either side renames the table this breaks loudly here rather than
    # quietly reporting nought again.
    builder = BUILDER.read_text()
    assert "CREATE TABLE" in builder
    assert " t(" in builder or " t (" in builder, (
        "the builder no longer writes a table called t")


def test_the_join_reads_the_same_database():
    assert "translations-db" in JOIN.read_text()


def test_a_database_without_the_chunk_count_still_reports_translations():
    # An older build wrote the translations without recording how many
    # chunks went in. The translations are the number being asked for.
    rest = REST.read_text()
    stats = rest[rest.index("static Map<String, Object> cacheStats()"):]
    assert "noBuiltTable" in stats, (
        "a missing built table would take the translation count with it")


def test_the_tile_is_not_called_a_cache():
    # It is the translation table for the run, not a cache of anything.
    summary = SUMMARY.read_text()
    assert "<h3>Cache</h3>" not in summary
    assert "<h3>Translations</h3>" in summary
    assert "distinct strings" in summary
