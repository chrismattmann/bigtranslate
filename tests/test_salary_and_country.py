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
"""Two fields the corpus has and the index was throwing away.

Challenge 8 of the XDATA employment set asks how compensation changes over
time and by locale. The salary column is in the corpus and was indexed as a
string, so it could not be averaged, bucketed or ranged over. Challenge 3
and the visualisation challenges ask about South America as a whole, and
there was no country field at all -- only 161 departments whose names a
reader is expected to recognise.

Neither is a clean column. salary is mostly words, and the numbers in it are
written four different ways. location holds the country only as the last of
several comma separated parts.
"""
import importlib.machinery
import importlib.util

from conftest import BIN, REPO

JOIN = BIN / "bt-join-index"
SCHEMA = (REPO / "solr" / "src" / "main" / "resources"
          / "bigtranslate" / "conf" / "schema.xml")


def _join():
    spec = importlib.util.spec_from_loader(
        "bt_join_index",
        importlib.machinery.SourceFileLoader("bt_join_index", str(JOIN)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSalaryBecomesANumber:

    def test_a_plain_figure(self):
        assert _join().parse_salary("5000") == 5000.0

    def test_a_dot_is_a_thousands_separator(self):
        # Latin America writes eight hundred thousand pesos as 800.000.
        # Read as a decimal point it is eight hundred, and a Colombian
        # salary becomes smaller than a Peruvian one.
        assert _join().parse_salary("800.000") == 800000.0
        assert _join().parse_salary("1.000.000") == 1000000.0

    def test_a_comma_is_one_too(self):
        assert _join().parse_salary("10,000") == 10000.0

    def test_a_range_becomes_its_midpoint(self):
        j = _join()
        assert j.parse_salary("$ 12000 - $ 13000") == 12500.0
        assert j.parse_salary("$1.200.000 - $1.500.000") == 1350000.0
        assert j.parse_salary("800 a 1000") == 900.0

    def test_two_numbers_with_nothing_between_them_are_not_a_range(self):
        # "2,5" parses to two numbers. Averaged as a range it becomes 3.5,
        # which is a salary of three and a half pesos.
        assert _join().parse_salary("2,5") is None

    def test_words_are_not_salaries(self):
        j = _join()
        for text in ("To be agreed", "In an interview", "Negotiable",
                     "to treat", "-", ""):
            assert j.parse_salary(text) is None, text

    def test_zero_means_unstated(self):
        # 417,082 records say 0. Indexed as zero they would be the floor of
        # every average.
        assert _join().parse_salary("0") is None

    def test_a_mistranslation_is_not_a_salary(self):
        # The model rendered a salary cell as "Table 1" on one country-day.
        # A bare 1 parsed out of that is a wage of one peso.
        assert _join().parse_salary("Table 1") is None

    def test_the_floor_keeps_out_what_is_not_pay(self):
        j = _join()
        assert j.parse_salary("99") is None
        assert j.parse_salary("100") == 100.0

    def test_a_sentence_with_figures_in_it_is_refused(self):
        # Three or more numbers and there is no telling which is the pay.
        assert _join().parse_salary("12000 a 13000 pesos mensuales 2013") is None

    def test_nothing_is_written_when_there_is_no_number(self):
        j = _join()
        document = {"salary": "To be agreed"}
        j.add_numeric_salary(document)
        assert "salary_d" not in document, (
            "an absent salary indexed as zero drags every average to the "
            "floor, and salary_d:[* TO *] stops meaning 'states a salary'")

    def test_it_is_written_when_there_is(self):
        j = _join()
        document = {"salary": "1.200.000"}
        j.add_numeric_salary(document)
        assert document["salary_d"] == 1200000.0


class TestCountryComesOutOfLocation:

    def test_the_last_part_is_the_country(self):
        j = _join()
        document = {"location": "Buenos Aires, Argentina"}
        j.add_country(document)
        assert document["country"] == "Argentina"

    def test_however_many_parts_there_are(self):
        j = _join()
        document = {"location": "Chacarita - Buenos Aires, Ciudad Autonoma "
                                "de Buenos Aires, Argentina"}
        j.add_country(document)
        assert document["country"] == "Argentina"

    def test_a_location_with_no_country_gets_none(self):
        j = _join()
        for text in ("Solo Bogota", "", None):
            document = {"location": text}
            j.add_country(document)
            assert "country" not in document, text

    def test_something_shaped_wrong_is_left_alone(self):
        # A street address rather than a country. Guessing here fills the
        # facet with one-record values and makes the panel unreadable.
        j = _join()
        document = {"location": "Calle 12, 1420"}
        j.add_country(document)
        assert "country" not in document


class TestTheSchemaCarriesThem:

    def test_both_fields_ship(self):
        schema = SCHEMA.read_text()
        assert 'name="salary_d" type="pdouble"' in schema
        assert 'name="country" type="string"' in schema

    def test_salary_is_not_required(self):
        # Most of the corpus does not state one.
        schema = SCHEMA.read_text()
        block = schema[schema.index('name="salary_d"'):]
        assert 'required="false"' in block[:200]

    def test_the_schema_warns_it_is_not_comparable_across_countries(self):
        # A Colombian peso and a Peruvian sol are three orders of magnitude
        # apart. An average over the whole corpus measures the country mix.
        schema = SCHEMA.read_text()
        assert "NOT COMPARABLE ACROSS COUNTRIES" in schema


class TestOneSpellingPerCountry:
    """The corpus writes each country several ways and a facet believes all.

    Over eight sampled days of the corpus:

        Mexico     'Mexico' 99,064   'mexico' 11,814   unaccented 8,634
        Peru       'Peru'   61,781   'peru'   10,845   unaccented 1,006
        Colombia   'Colombia' 66,302 'colombia' 9,489
        Argentina  'Argentina' 27,730 'argentina' 3,707

    Left alone the country facet spends three of its six buckets on Mexico,
    and the salary panel draws it as three countries with three different
    medians.
    """

    def test_accents_are_stripped(self):
        assert _join().canonical_country("México") == "Mexico"
        assert _join().canonical_country("Perú") == "Peru"

    def test_case_is_normalised(self):
        j = _join()
        assert j.canonical_country("colombia") == "Colombia"
        assert j.canonical_country("ARGENTINA") == "Argentina"

    def test_every_spelling_of_mexico_lands_together(self):
        j = _join()
        spellings = {j.canonical_country(s)
                     for s in ("México", "méxico", "Mexico", "mexico",
                               "MEXICO")}
        assert spellings == {"Mexico"}, spellings

    def test_two_word_countries_survive(self):
        j = _join()
        assert j.canonical_country("Puerto Rico") == "Puerto Rico"
        assert j.canonical_country("puerto rico") == "Puerto Rico"

    def test_the_document_gets_the_canonical_form(self):
        j = _join()
        document = {"location": "Lima, Perú"}
        j.add_country(document)
        assert document["country"] == "Peru"

    def test_a_city_only_location_gets_no_country(self):
        # 46% of records have only a city in that cell -- the same records
        # the geo-fixing never reached. Absent, not guessed.
        j = _join()
        document = {"location": "Bogota"}
        j.add_country(document)
        assert "country" not in document


class TestTheApostropheIsAMillionsSeparator:
    """$1'700,000 is one point seven million Colombian pesos.

    Found by reading what the index actually stored, after the join:

        salary   "$1 '700,000 Colombian pesos + Extr"
        salary_d 700,000

    The leading 1 came off as a number of its own, fell below the floor as
    noise, and the salary was stored as the remainder -- understated two and
    a half times, silently, on 403,182 postings. All of them Colombian,
    because the apostrophe is a Colombian convention.
    """

    def test_the_whole_figure_survives(self):
        assert _join().parse_salary("$1'700,000") == 1700000.0

    def test_however_it_is_spaced(self):
        j = _join()
        for text in ("$1 '700,000 Colombian pesos + Extras",
                     "$ 1' 700.000", "$1' 700,000"):
            assert j.parse_salary(text) == 1700000.0, text

    def test_a_space_inside_the_figure_does_not_split_it(self):
        assert _join().parse_salary("$ 1'000 000") == 1000000.0

    def test_a_range_written_that_way_still_averages(self):
        assert _join().parse_salary("$1'200,000 - $1'500,000") == 1350000.0

    def test_a_range_without_apostrophes_is_untouched(self):
        # The collapse is gated on the apostrophe and stops at the dash, so
        # an ordinary range does not become one enormous number.
        assert _join().parse_salary("$ 12000 - $ 13000") == 12500.0

    def test_a_sentence_with_figures_is_still_refused(self):
        assert _join().parse_salary(
            "12000 a 13000 pesos mensuales 2013") is None
