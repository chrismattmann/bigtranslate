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
"""The glossary reaching the pipeline that actually runs.

The glossary was written for a documented set of model failures -- it left
"Inmediato" untranslated in 151 of 211 records on a sample country-day,
rendered "correo electronico" as "default mail", and turned "Asap" into
"Asaph". The W2 rewrite never passed it. In a full corpus run "Inmediato"
was the value of 75,420,702 documents' start field, untranslated.

These tests are about the wiring, because the wiring is what was missing:
lookup itself is covered in test_glossary.py.
"""

import importlib.machinery
import importlib.util
import json
import sqlite3

import pytest

from conftest import BIN, CONF, POLICY, WORKFLOW_POLICY, Glossary, shim


def _load(name):
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(name.replace("-", "_"),
                                             str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUntranslatable:
    """A string with no letter in it is not language.

    The rule used to ask for no letter *or digit*, which let every numeric
    string in the corpus through to the model. Salaries are the field where
    that showed.
    """

    @pytest.mark.parametrize("value", ["!", "!!!", "-", "-----------", "###",
                                       ",.", "   ", "***"])
    def test_punctuation_is_untranslatable(self, value):
        assert shim.is_untranslatable(value)

    @pytest.mark.parametrize("value", ["$ 12000 - $ 13000", "$ 1500000-2000000",
                                       "!.500.000", "!000", "24/7", "1.100.000",
                                       "2013-05-07"])
    def test_numbers_are_untranslatable_too(self, value):
        # These went to the model and came back wrong. 2,805 distinct salary
        # ranges collapsed onto "Table 1"; "!.500.000" became "500,000!" and
        # "!000" became "- $1,000.", a value that was never in the source.
        # Measured over 2,286,371 translations: 45,115 strings contain no
        # letter and the model altered 31,196 of them. The old rule caught
        # 467.
        assert shim.is_untranslatable(value)

    @pytest.mark.parametrize("value", ["Inmediato", "6 months", "A1", "40 hs",
                                       "$800.000 - 1.100.000 (Segun estudios)",
                                       "Administrativa (oeste)"])
    def test_anything_with_a_letter_is_still_translated(self, value):
        # A salary that carries words is worth translating, and this is what
        # keeps that working rather than throwing the field away wholesale.
        assert not shim.is_untranslatable(value)

    def test_this_is_the_shape_that_produced_an_apology(self):
        # Asked to translate "!" the model answered "- I'm sorry." -- which
        # reached 4.7 million documents as a duration and a start date.
        assert shim.is_untranslatable("!")


class TestResolveWithGlossary:

    def setup_method(self):
        self.chunk = _load("bt-translate-chunk")

    def test_glossary_entries_never_reach_the_model(self):
        g = Glossary({"Inmediato": "Immediate"})
        resolved, remaining = self.chunk.resolve_with_glossary(
            ["Inmediato", "Ingeniero"], g, shim.is_untranslatable)
        assert resolved == {"Inmediato": "Immediate"}
        assert remaining == ["Ingeniero"]

    def test_casings_collapse_onto_one_entry(self):
        g = Glossary({"Inmediato": "Immediate"})
        resolved, remaining = self.chunk.resolve_with_glossary(
            ["Inmediato", "inmediato", "INMEDIATO"], g, shim.is_untranslatable)
        assert set(resolved.values()) == {"Immediate"}
        assert remaining == []

    def test_punctuation_is_resolved_to_itself(self):
        resolved, remaining = self.chunk.resolve_with_glossary(
            ["!", "---"], Glossary(), shim.is_untranslatable)
        assert resolved == {"!": "!", "---": "---"}
        assert remaining == []

    def test_an_empty_glossary_sends_everything_to_the_model(self):
        resolved, remaining = self.chunk.resolve_with_glossary(
            ["Inmediato"], Glossary(), shim.is_untranslatable)
        assert resolved == {}
        assert remaining == ["Inmediato"]


class TestBuildTranslationDb:
    """Correcting chunks already on disk, without translating again."""

    def _chunk(self, tmp_path, pairs):
        d = tmp_path / "translated"
        d.mkdir(exist_ok=True)
        (d / "chunk-00000.json").write_text(json.dumps(pairs),
                                            encoding="utf-8")
        return d

    def _rows(self, out):
        conn = sqlite3.connect(str(out))
        try:
            return dict(conn.execute("SELECT s, e FROM t"))
        finally:
            conn.close()

    def test_the_glossary_overrides_what_the_model_returned(self, tmp_path):
        # The thirteen hours of translation on disk stay on disk: the
        # override is a pure function of the source string.
        db = _load("bt-build-translation-db")
        d = self._chunk(tmp_path, {"Inmediato": "Inmediato"})
        out = tmp_path / "t.sqlite"
        db.build(str(d), str(out), Glossary({"Inmediato": "Immediate"}),
                 shim.is_untranslatable)
        assert self._rows(out) == {"Inmediato": "Immediate"}

    def test_punctuation_is_restored_to_its_source(self, tmp_path):
        db = _load("bt-build-translation-db")
        d = self._chunk(tmp_path, {"!": "- I'm sorry."})
        out = tmp_path / "t.sqlite"
        db.build(str(d), str(out), Glossary(), shim.is_untranslatable)
        assert self._rows(out) == {"!": "!"}

    def test_model_output_is_kept_where_nothing_overrides_it(self, tmp_path):
        db = _load("bt-build-translation-db")
        d = self._chunk(tmp_path, {"Ingeniero": "Engineer"})
        out = tmp_path / "t.sqlite"
        db.build(str(d), str(out), Glossary({"Inmediato": "Immediate"}),
                 shim.is_untranslatable)
        assert self._rows(out) == {"Ingeniero": "Engineer"}


class TestTheWiring:
    """The bug was never in the lookup; it was that nothing passed it."""

    def test_translate_chunk_is_given_the_glossary(self):
        text = (POLICY / "no_filter" / "PgeConfig_TranslateChunk.xml").read_text()
        assert "--glossary [TranslateGlossary]" in text

    def test_the_translation_db_build_is_given_the_glossary(self):
        text = (POLICY / "no_filter" / "PgeConfig_JoinIndex.xml").read_text()
        assert "--glossary [TranslateGlossary]" in text

    def test_the_tasks_that_use_it_define_it(self):
        text = (WORKFLOW_POLICY / "tasks.xml").read_text()
        # W1's BigTranslate_Task, plus the two W2 tasks that now need it.
        assert text.count('name="TranslateGlossary"') == 3

    def test_the_glossary_ships(self):
        assert (CONF / "glossary.es-en.tsv").exists()

    def test_the_documented_failures_are_still_covered(self):
        # The entries exist because of specific observed errors; a glossary
        # that lost them would pass every other test here.
        g = Glossary.load(str(CONF / "glossary.es-en.tsv"))
        assert g.lookup("Inmediato") == "Immediate"
        assert g.lookup("correo electronico") == "Email"
        assert g.lookup("Asap") == "Immediate"
        assert g.lookup("Medio Tiempo") == "Part Time"
