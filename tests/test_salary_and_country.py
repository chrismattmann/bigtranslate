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
