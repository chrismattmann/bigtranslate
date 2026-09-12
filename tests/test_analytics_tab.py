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
"""The Analytics tab, and the index it reads.

The panels answer questions from the XDATA employment dataset's own
challenge list. What they can answer is a property of the schema, not of the
drawing, so the two are checked together: a tokenised title is what makes
"which of these are driving jobs" a question the index can be asked at all.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "solr/src/main/resources/bigtranslate/conf/schema.xml"
GLOSS = ROOT / "webapps/gloss/src/main/webapp/resources/src"
APP = GLOSS / "App.vue"
PANEL = GLOSS / "components/AnalyticsPanel.vue"
LOGIC = GLOSS / "analytics.js"


class TestTheSchemaCanBeAsked:
    """Sector questions need something tokenised to ask."""

    @pytest.mark.parametrize("field", ["title_txt", "salary_txt"])
    def test_the_tokenised_copy_exists(self, field):
        root = ET.parse(SCHEMA).getroot()
        found = [f for f in root.iter("field") if f.get("name") == field]
        assert found, "%s is not declared" % field
        assert found[0].get("type") == "text_general", (
            "%s is not tokenised, so a word in it cannot be searched for"
            % field)

    @pytest.mark.parametrize("source", ["title", "salary"])
    def test_the_copy_is_actually_made(self, source):
        root = ET.parse(SCHEMA).getroot()
        pairs = {(c.get("source"), c.get("dest")) for c in root.iter("copyField")}
        assert (source, source + "_txt") in pairs, (
            "%s is declared but nothing copies into it" % (source + "_txt"))

    def test_the_string_fields_are_still_string(self):
        # The tokenised fields are additions. Faceting, grouping and the
        # exact-match filters in the Table tab all need the string ones.
        root = ET.parse(SCHEMA).getroot()
        types = {f.get("name"): f.get("type") for f in root.iter("field")}
        for name in ("title", "salary", "department", "location", "jobtype"):
            assert types.get(name) == "string", name


class TestTheTabIsWired:

    def test_the_panel_ships(self):
        assert PANEL.is_file()
        assert LOGIC.is_file()

    def test_the_tab_is_reachable(self):
        app = APP.read_text()
        assert "AnalyticsPanel" in app, "the panel is never imported"
        assert "go('analytics')" in app, "there is no button to reach it"
        assert "raw === 'analytics'" in app, (
            "the tab cannot be linked to or reloaded into")

    def test_every_panel_names_its_challenge_question(self):
        # The panels exist to answer a published list. A chart that does not
        # say which question it answers is decoration.
        panel = PANEL.read_text()
        for question in ("Challenge 12", "Challenge 2 and 10", "Challenge 14",
                         "Challenge 1", "Challenge 5"):
            assert question in panel, "no panel claims %s" % question

    def test_the_modelled_panels_say_that_they_are_modelled(self):
        # A dashed line through eighteen points is a projection, and calling
        # it a forecast is the most confident wrong thing this tab could say.
        panel = PANEL.read_text()
        assert "projection, not a forecast" in panel
        assert "R²" in panel, "the fit is not shown, so a bad one looks fine"

    def test_the_sector_caveat_is_shown_when_it_applies(self):
        # Matching sectors against the catch-all text field also matches
        # company names and salary notes. Until title_txt is indexed that is
        # what the panels are built on, and the reader is told.
        panel = PANEL.read_text()
        assert "catch-all" in panel
        assert "sectorField === 'text'" in panel, (
            "the caveat is not conditioned on the field actually used")

    def test_the_arithmetic_is_separable_from_the_drawing(self):
        # analytics.js is unit tested by npm test; a chart that computed its
        # own numbers inline would not be.
        panel = PANEL.read_text()
        for fn in ("project", "opportunities", "zone", "growthRate",
                   "wholeMonths"):
            assert fn in panel, "%s is not used by the panel" % fn
        logic = LOGIC.read_text()
        assert "import" not in logic.split("export")[0] or "d3" not in logic, (
            "the logic module pulls in the drawing library")


class TestTheLogicIsTested:

    def test_the_test_file_ships(self):
        assert (GLOSS / "analytics.test.js").is_file()

    def test_npm_test_would_pick_it_up(self):
        pkg = (GLOSS.parent / "package.json").read_text()
        assert "src/*.test.js" in pkg, (
            "the test script does not glob the new file")
