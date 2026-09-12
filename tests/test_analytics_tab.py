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

    def test_the_charts_are_drawn_after_the_dom_exists(self):
        """The svg elements live in the template's v-else.

        Drawing while loading is still true finds every ref null and returns
        having drawn nothing, silently: a chart with no data to plot looks
        exactly like one that was never asked to. The panel rendered five
        empty boxes and reported no error.
        """
        panel = PANEL.read_text()
        body = panel[panel.index("async function load()"):]
        body = body[:body.index("function redraw()")]
        for fn in ("drawHours(", "drawLifetimes(", "drawZones(",
                   "drawTrends(", "drawGaps("):
            assert fn not in body, (
                "%s is called from load(), before Vue has rendered the "
                "elements it draws into" % fn)
        assert "await nextTick()" in body, (
            "nothing waits for the template to be flushed")
        assert body.index("loading.value = false") < body.index("await nextTick()")

    def test_a_resize_redraws_rather_than_refetches(self):
        # The composite query takes about six seconds; issuing it per frame
        # of a window drag would be unusable.
        panel = PANEL.read_text()
        observer = panel[panel.index("new ResizeObserver"):]
        observer = observer[:observer.index("observer.observe")]
        assert "redraw()" in observer
        assert "load()" not in observer

    def test_the_resize_guard_breaks_the_loop(self):
        # Drawing changes the height of the element being observed, so
        # redrawing on any size change is a loop the browser breaks with
        # "ResizeObserver loop completed with undelivered notifications".
        panel = PANEL.read_text()
        assert "drawnAt" in panel, "no record of the width already drawn at"
        observer = panel[panel.index("new ResizeObserver"):]
        observer = observer[:observer.index("observer.observe")]
        assert "width === drawnAt" in observer, (
            "the observer does not compare against the last drawn width")

    def test_the_lifetime_panel_counts_jobs_not_rows(self):
        """119 million rows are 2.1 million jobs seen once a day each.

        Averaging days-up over rows weights every posting by its own length:
        a job up for two hundred days contributes two hundred rows each
        saying two hundred days. It answered about 100 days. One row per url
        answers about 13, and the difference is the whole result.
        """
        panel = PANEL.read_text()
        assert "{!collapse field=url}" in panel, (
            "the lifetime average is taken over rows, which is length biased")
        note = panel[panel.index("Mean days between first and last seen"):]
        note = note[:note.index("</p>")]
        assert "distinct jobs" in note
        assert "rows" in note, "the note does not say which was counted"

    def test_growth_is_measured_on_share_not_count(self):
        """Collection wound down; counts fall with it.

        Postings per month drop about 7% a month across this corpus, so every
        sector's raw count drops too and every sector reads as declining.
        Measured that way all nine had negative growth, no region qualified
        for an opening anywhere, and the panel drew nothing at all -- which
        reads as a broken chart rather than as an answer.
        """
        panel = PANEL.read_text()
        gaps = panel[panel.index("function drawGaps"):]
        gaps = gaps[:gaps.index("onMounted")]
        assert "shareSeries(buckets" in gaps, (
            "growth is computed from raw counts, which measures the scraper")
        trends = panel[panel.index("function drawTrends"):]
        trends = trends[:trends.index("function drawGaps")]
        assert "shareSeries(buckets" in trends, (
            "the sparklines plot raw counts, so every sector slopes down")

    def test_the_intro_describes_the_dataset(self):
        # The panels are about a specific corpus with specific quirks, and a
        # reader who does not know them cannot read the charts: that a job is
        # recorded once per day it was up is why two panels count different
        # things, and that the scrape wound down is why two others use shares.
        panel = PANEL.read_text()
        intro = panel[:panel.index('<p v-if="error"')]
        assert "computrabajo" in intro, "the source is not named"
        for country in ("Mexico", "Argentina", "Colombia", "Peru"):
            assert country in intro, "%s is not named" % country
        assert "Spanish" in intro, "why any of this needed translating"
        assert "once a day" in intro, (
            "the daily re-observation is not explained, and it is why the "
            "row count and the job count differ")
        assert "challenge questions" in intro

    def test_the_intro_uses_the_width_it_is_given(self):
        # Capped at 74ch it read as text collapsed against the left edge of a
        # wide window rather than as a measure.
        panel = PANEL.read_text()
        style = panel[panel.index("<style scoped>"):]
        intro_rule = [line for line in style.splitlines()
                      if line.strip().startswith(".intro p")
                      or line.strip().startswith(".intro-text p")]
        for line in intro_rule:
            assert "max-width" not in line, (
                "the introduction is still capped: " + line.strip())
        assert ".intro-text" in style, "the paragraphs have no column context"
        assert "columns: 2" in style, (
            "a wide window gets one very long line instead of columns")

    def test_the_intro_gives_both_counts(self):
        panel = PANEL.read_text()
        intro = panel[:panel.index('<p v-if="error"')]
        assert "totalLabel" in intro and "jobLabel" in intro, (
            "the reader is given one number where the corpus has two")

    def test_an_empty_result_says_so(self):
        # An empty panel is indistinguishable from a broken one, which is how
        # the openings panel was first reported.
        panel = PANEL.read_text()
        assert "No openings found." in panel

    def test_every_chart_can_be_hovered(self):
        panel = PANEL.read_text()
        assert panel.count("hoverable(") >= 6, (
            "not every chart attaches a tooltip")
        for fn in ("drawHours", "drawLifetimes", "drawZones", "drawTrends",
                   "drawGaps"):
            body = panel[panel.index("function %s" % fn):]
            body = body[:body.index("\n    }", body.index("{"))]
            assert "hoverable(" in body, "%s has no hover" % fn

    def test_every_chart_carries_a_key(self):
        # "Office and admin +3" against nine colours is not readable without
        # one.
        panel = PANEL.read_text()
        assert "function legend(" in panel
        assert "function sectorKey(" in panel
        hours = panel[panel.index("function drawHours"):]
        hours = hours[:hours.index("function drawLifetimes")]
        assert "legend(sel" in hours, "the hours chart has no key"
        zones = panel[panel.index("function drawZones"):]
        zones = zones[:zones.index("function drawTrends")]
        assert "sectorKey(sel" in zones, "the zoning chart has no key"
        gaps = panel[panel.index("function drawGaps"):]
        gaps = gaps[:gaps.index("onMounted")]
        assert "no opening" in gaps and "strongest" in gaps, (
            "the heatmap has no colour ramp to read a shade against")

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
