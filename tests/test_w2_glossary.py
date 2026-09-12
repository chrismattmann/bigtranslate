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

    @pytest.mark.parametrize("value", ["Inmediato", "6 months", "otro", "Caja",
                                       "3 d\u00edas", "M\u00ednimo",
                                       "$800.000 - 1.100.000 (Segun estudios)",
                                       "Administrativa (oeste)"])
    def test_real_words_are_still_translated(self, value):
        # A salary that carries words is worth translating, and this is what
        # keeps that working rather than throwing the field away wholesale.
        # Four letters is where real words start: "otro", "Caja" and "alto"
        # come back correctly.
        assert not shim.is_untranslatable(value)

    @pytest.mark.parametrize("value", ["i", "o", "9AM", "Sqe", "Ilo", "N/A",
                                       "A1", "40 hs", "P.S", "lun"])
    def test_too_few_letters_to_be_language(self, value):
        # One letter was not enough of a bar. A value with a letter or two is
        # a code, an abbreviation or a stray character, and the model invents
        # language for it exactly as it did for punctuation: "i" came back as
        # "& Add", "Sqe" as "& Left", "9AM" as "b.", "N/A" as "N / A".
        #
        # Measured over the 1,460,000 distinct strings of a full run: 36,140
        # have fewer than four letters and 12,321 of them came back altered.
        assert shim.is_untranslatable(value)

    @pytest.mark.parametrize("value", ["S/ 900=", "S/.30", "s/.25", "S/ 1000"])
    def test_a_sol_amount_is_not_language_either(self, value):
        # What the digit rule left open. A sol amount carries a single letter,
        # so these went to the model on the strength of one "S" and came back
        # as "S / 900" and "S / 2007 / 1" -- the same invented salary the
        # digit rule was written to stop.
        assert shim.is_untranslatable(value)

    def test_the_threshold_can_be_tried_without_a_code_change(self):
        # So a corpus can be measured at five before anyone commits to it.
        assert shim.is_untranslatable("otro", min_letters=5)
        assert not shim.is_untranslatable("otro", min_letters=4)

    def test_a_short_term_that_must_translate_goes_in_the_glossary(self):
        # The rule makes short strings pass through unchanged, which is safe
        # but not useful in a duration column. The glossary is consulted
        # first, so an entry still wins.
        chunk = _load("bt-translate-chunk")
        resolved, remaining = chunk.resolve_with_glossary(
            ["dia", "Sqe"], Glossary({"dia": "day"}), shim.is_untranslatable)
        assert resolved == {"dia": "day", "Sqe": "Sqe"}
        assert remaining == []

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


class TestShortTimeUnitsAreCovered:
    """The terms the new threshold would otherwise pass through untouched.

    Unchanged is safe but not useful in a duration or start column, and the
    model got these wrong or got them inconsistently: "hrs" came back as
    "timer", "mes" as "month" in one chunk and "We" in another, and "dia" as
    "He" while the tilde'd "dia" came back as "Day".
    """

    def setup_method(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        self.path = (root / "distribution" / "src" / "main" / "resources"
                     / "conf" / "glossary.es-en.tsv")

    def _entries(self):
        out = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                out[parts[0].strip().lower()] = parts[1].strip()
        return out

    @pytest.mark.parametrize("term,english", [
        ("dia", "day"), ("día", "day"), ("mes", "month"),
        ("hrs", "hours"), ("ano", "year"), ("año", "year"),
    ])
    def test_the_term_is_covered(self, term, english):
        assert self._entries().get(term) == english

    def test_every_entry_is_the_glossarys_two_column_shape(self):
        # A stray third column silently becomes part of the English value.
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            assert line.count("\t") == 1, "not source<TAB>target: %r" % line

    def test_each_covered_term_would_otherwise_be_suppressed(self):
        # If one of these grew past the threshold the entry would be dead
        # weight rather than a fix, and nothing would say so.
        for term in ("dia", "mes", "hrs", "ano"):
            assert shim.is_untranslatable(term)
