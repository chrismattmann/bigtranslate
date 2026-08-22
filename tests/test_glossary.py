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
"""Glossary lookup for the Pantogloss translation step."""

import pytest

from conftest import CONF, Glossary


class TestLookup:
    def test_exact_match(self):
        g = Glossary({"Tiempo Completo": "Full Time"})
        assert g.lookup("Tiempo Completo") == "Full Time"

    def test_is_case_insensitive(self):
        # The model treats casings differently: on a sample country-day it left
        # "Inmediato" untranslated while rendering "inmediato" correctly. One
        # entry has to cover every casing.
        g = Glossary({"Inmediato": "Immediate"})
        assert g.lookup("inmediato") == "Immediate"
        assert g.lookup("INMEDIATO") == "Immediate"
        assert g.lookup("Inmediato") == "Immediate"

    def test_ignores_surrounding_whitespace(self):
        g = Glossary({"Inmediato": "Immediate"})
        assert g.lookup("  Inmediato  ") == "Immediate"

    def test_unknown_value_returns_none(self):
        g = Glossary({"Tiempo Completo": "Full Time"})
        assert g.lookup("Analista Programador") is None

    def test_none_input_returns_none(self):
        assert Glossary({"a": "b"}).lookup(None) is None

    def test_empty_glossary_resolves_nothing(self):
        assert Glossary().lookup("Tiempo Completo") is None


class TestComponentResolution:
    """Controlled-vocabulary fields hold comma-separated lists."""

    def test_resolves_every_component(self):
        g = Glossary({"Medio Tiempo": "Part Time", "Desde Casa": "Work From Home"})
        assert g.lookup("Medio Tiempo, Desde Casa") == "Part Time, Work From Home"

    def test_resolves_three_components(self):
        g = Glossary({"Tiempo Completo": "Full Time",
                      "Medio Tiempo": "Part Time",
                      "Por Horas": "Hourly"})
        assert (g.lookup("Tiempo Completo, Medio Tiempo, Por Horas")
                == "Full Time, Part Time, Hourly")

    def test_declines_when_any_component_is_unknown(self):
        # Falling back to the model for the whole value is better than emitting
        # a half-translated string.
        g = Glossary({"Medio Tiempo": "Part Time"})
        assert g.lookup("Medio Tiempo, Algo Desconocido") is None

    def test_component_match_is_case_insensitive(self):
        g = Glossary({"Medio Tiempo": "Part Time", "Desde Casa": "Work From Home"})
        assert g.lookup("medio tiempo, DESDE CASA") == "Part Time, Work From Home"

    def test_whole_value_entry_beats_component_resolution(self):
        g = Glossary({
            "Medio Tiempo": "Part Time",
            "Desde Casa": "Work From Home",
            "Medio Tiempo, Desde Casa": "Part Time Remote",
        })
        assert g.lookup("Medio Tiempo, Desde Casa") == "Part Time Remote"

    def test_does_not_split_a_value_with_an_empty_component(self):
        g = Glossary({"Medio Tiempo": "Part Time"})
        assert g.lookup("Medio Tiempo, ") is None

    def test_salary_figures_are_left_alone(self):
        # Salary values contain commas but are not term lists.
        g = Glossary({"Tiempo Completo": "Full Time"})
        assert g.lookup("$ 12,000.00") is None


class TestLoad:
    def _write(self, tmp_path, text):
        f = tmp_path / "glossary.tsv"
        f.write_text(text, encoding="utf-8")
        return f

    def test_reads_tab_separated_pairs(self, tmp_path):
        f = self._write(tmp_path, "Tiempo Completo\tFull Time\n")
        assert Glossary.load(str(f)).lookup("Tiempo Completo") == "Full Time"

    def test_skips_comments_and_blank_lines(self, tmp_path):
        f = self._write(tmp_path, "# a comment\n\n   \nInmediato\tImmediate\n")
        g = Glossary.load(str(f))
        assert len(g) == 1
        assert g.lookup("Inmediato") == "Immediate"

    def test_skips_malformed_lines(self, tmp_path):
        f = self._write(tmp_path, "no tab here\nInmediato\tImmediate\n")
        g = Glossary.load(str(f))
        assert len(g) == 1

    def test_strips_padding_around_fields(self, tmp_path):
        f = self._write(tmp_path, "  Inmediato  \t  Immediate  \n")
        assert Glossary.load(str(f)).lookup("Inmediato") == "Immediate"

    def test_reads_accented_sources(self, tmp_path):
        f = self._write(tmp_path, "Prácticas\tInternship\n")
        assert Glossary.load(str(f)).lookup("Prácticas") == "Internship"


@pytest.fixture(scope="module")
def glossary():
    return Glossary.load(str(CONF / "glossary.es-en.tsv"))


class TestShippedGlossary:
    """The file that actually ships in the distribution."""

    def test_loads(self, glossary):
        assert len(glossary) > 40

    @pytest.mark.parametrize(
        "source,expected",
        [
            # Each of these was observed wrong in a real run.
            ("Inmediato", "Immediate"),          # was left untranslated
            ("Medio Tiempo", "Part Time"),       # was "Half Time" / "Middle Time"
            ("Correo Electronico", "Email"),     # was "default mail"
            ("Asap", "Immediate"),               # was "Asaph"
            ("Indefinido", "Indefinite"),        # was "undefined"
            ("Tiempo Completo", "Full Time"),
        ],
    )
    def test_corrects_known_bad_translations(self, glossary, source, expected):
        assert glossary.lookup(source) == expected

    def test_covers_the_composite_jobtype_values(self, glossary):
        assert glossary.lookup("Medio Tiempo, Desde Casa") == "Part Time, Work From Home"
        assert glossary.lookup("Tiempo Completo, Desde Casa") == "Full Time, Work From Home"

    def test_every_target_is_non_empty(self, glossary):
        for source, target in glossary.entries.items():
            assert target.strip(), "empty target for %r" % source
