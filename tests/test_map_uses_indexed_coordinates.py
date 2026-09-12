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
