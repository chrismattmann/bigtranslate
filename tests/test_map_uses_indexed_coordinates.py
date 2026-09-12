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
"""The map draws postings where the data says they are.

The corpus carries coordinates for 79 million of its documents, produced by
the geo-fixing service the dataset description explains. The map used twenty
of them. It read the first thousand documents the index returned -- no sort,
no grouping -- and documents come back in index order from a corpus loaded a
file at a time, so that thousand was one or two cities. Every other location
was re-geocoded from a name like "Monterrey, NL, Mexico", which a general
purpose geocoder may place anywhere.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOLR_SUPPORT = (ROOT / "webapps/gloss-services/src/main/java/org/bigtranslate"
                / "gloss/SolrSupport.java")


def _sample_coords():
    text = SOLR_SUPPORT.read_text()
    start = text.index("private Map<String, SampleCoord> sampleCoords()")
    return text[start:text.index("\n  }", start)]


def test_coordinates_come_per_location_not_per_document():
    body = _sample_coords()
    assert "rows=1000" not in body, (
        "still reading an arbitrary thousand documents, which in index order "
        "is one or two cities")
    assert "type:terms,field:location" in body, (
        "coordinates are not grouped by the thing the map draws")


def test_it_asks_for_the_same_locations_the_map_draws():
    # Two limits that must agree: a location the map faceted but the
    # coordinate query did not would silently fall back to the geocoder.
    text = SOLR_SUPPORT.read_text()
    assert "static final int MAP_LOCATIONS" in text
    assert text.count("MAP_LOCATIONS") >= 3, (
        "the facet limit and the coordinate limit are not the same constant")
    assert "facet.limit=500" not in text


def test_the_origin_is_not_a_place():
    # A third of the corpus has 0,0: never geo-fixed. Drawn literally that is
    # a bubble in the Atlantic off west Africa.
    body = _sample_coords()
    assert "== 0.0" in body and "continue" in body, (
        "a location whose only coordinate is the origin would be plotted")


def test_the_geocoder_is_still_there_for_what_the_index_lacks():
    text = SOLR_SUPPORT.read_text()
    assert "geocoder.geocode(location)" in text, (
        "locations with no indexed coordinate would simply vanish")


class TestCoordinatesAreAlsoNumbers:
    """latitude and longitude are strings, so a range over them is text.

    Asking for latitude between -56 and 14, which is South America, returns
    nothing at all. They have to stay strings: they are required and the
    corpus leaves them blank in about 1% of records, which is not a number.
    So the numbers go alongside them.
    """

    SCHEMA = ROOT / "solr/src/main/resources/bigtranslate/conf/schema.xml"
    JOIN = ROOT / "distribution/src/main/resources/bin/bt-join-index"

    def _schema(self):
        import xml.etree.ElementTree as ET
        return ET.parse(self.SCHEMA).getroot()

    def test_the_numeric_field_type_is_declared(self):
        types = {t.get("name"): t for t in self._schema().iter("fieldType")}
        assert "pdouble" in types, "no numeric type to declare them as"
        assert types["pdouble"].get("docValues") == "true", (
            "without docValues a coordinate can be matched but not averaged "
            "or bucketed, which is the point of having it")

    def test_both_coordinates_have_a_numeric_twin(self):
        fields = {f.get("name"): f for f in self._schema().iter("field")}
        for name in ("latitude_d", "longitude_d"):
            assert name in fields, "%s is not declared" % name
            assert fields[name].get("type") == "pdouble"

    def test_the_numeric_twin_is_not_required(self):
        # A blank cell has no number in it, and a required field would drop
        # the record for want of one.
        fields = {f.get("name"): f for f in self._schema().iter("field")}
        for name in ("latitude_d", "longitude_d"):
            assert fields[name].get("required") != "true", name

    def test_nothing_copies_into_it(self):
        # copyField hands the raw value over, and "" does not parse as a
        # double: it would fail the whole document.
        copies = {(c.get("source"), c.get("dest"))
                  for c in self._schema().iter("copyField")}
        for pair in (("latitude", "latitude_d"), ("longitude", "longitude_d")):
            assert pair not in copies, (
                "%s is copied, and a blank cell would fail the document" % str(pair))

    def test_the_join_writes_them(self):
        assert "add_numeric_coordinates" in self.JOIN.read_text()

    def test_the_origin_leaves_them_absent(self):
        # Zero is not a missing value, it is a place in the Gulf of Guinea,
        # and a third of this corpus was never geo-fixed. Indexed as zero,
        # every average over latitude is dragged toward it by forty million
        # records.
        body = self.JOIN.read_text()
        fn = body[body.index("def add_numeric_coordinates"):]
        fn = fn[:fn.index("\ndef ", 1)]
        assert 'pop("latitude_d"' in fn and 'pop("longitude_d"' in fn, (
            "a never-geo-fixed record would be plotted off west Africa")
