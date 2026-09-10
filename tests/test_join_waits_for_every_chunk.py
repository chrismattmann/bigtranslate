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
""""Translating has finished" is a count, not a pause.

The join was held until no new translation had been catalogued for two
minutes, on the reasoning that a chunk takes minutes to translate so a gap
that long must be the end of the work.

Sixteen chunks translate at once across two nodes and they do not finish
evenly. On a 458 chunk run there were seventeen gaps of two minutes or more,
the longest 264 seconds, and the first came at 11:59 with 155 chunks still to
do. The condition passed there, and the join sat queued from that moment
against a third of a corpus.

Nothing came of it: the join waits four hours for its chunks, and it could
not get a slot on the manager before they arrived. Neither of those is a
reason to keep asking a question whose answer is wrong.

Extract catalogues one EmploymentStringChunk per chunk before any translation
starts, so the number to reach is known rather than inferred from silence.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "workflow" / "src" / "main" / "resources" / "policy"
CONDITIONS = POLICY / "conditions.xml"
TASKS = POLICY / "tasks.xml"


def condition(condition_id):
    root = ET.parse(CONDITIONS).getroot()
    for c in root.iter("condition"):
        if c.get("id") == condition_id:
            return c
    raise AssertionError("no condition %s" % condition_id)


def properties(element):
    return {p.get("name"): p.get("value") for p in element.iter("property")}


SETTLED = "urn:bigtranslate:TranslationsSettled"


class TestTheJoinWaitsForEveryChunk:

    def test_it_compares_counts_rather_than_waiting_for_quiet(self):
        c = condition(SETTLED)
        assert c.get("class").endswith("ProductCountMatchesCondition"), (
            "a pause in a run of hundreds of chunks is not the end of it")
        props = properties(c)
        assert "QuietSeconds" not in props, (
            "any quiet period is a guess, and this one passed with 155 "
            "chunks left to translate")

    def test_it_counts_the_translations_against_the_extractions(self):
        props = properties(condition(SETTLED))
        assert props["ProductTypeName"] == "EmploymentTranslatedChunk"
        assert props["MatchesProductTypeName"] == "EmploymentStringChunk"

    def test_those_are_the_types_the_stages_actually_catalogue(self):
        # A condition naming a type nothing produces holds forever, and the
        # run stops with every translation done and no index.
        catalogued = {p.get("value")
                      for p in ET.parse(TASKS).getroot().iter("property")
                      if p.get("name") == "ProductType"}
        props = properties(condition(SETTLED))
        for key in ("ProductTypeName", "MatchesProductTypeName"):
            assert props[key] in catalogued, (
                "%s names [%s], which no task catalogues" % (key, props[key]))

    def test_nothing_can_match_before_extract_has_run(self):
        # Without a floor, nought translated matches nought extracted and
        # the join starts immediately against an empty corpus.
        props = properties(condition(SETTLED))
        assert int(props["MinCount"]) >= 1

    def test_the_condition_still_runs_on_the_manager(self):
        # It reads the manager's File Manager, and it is re-asked until it
        # passes, so it must not sit in the queue the translations use.
        assert properties(condition(SETTLED))["QueueName"] == "conditions"


class TestThePolicyIsWellFormed:
    """A double hyphen inside an XML comment is not a comment.

    It has taken this deployment down once already: an unparseable policy
    file stops the Resource Manager at startup and the Workflow Manager with
    it, and the error names a column rather than a cause.
    """

    def _xml_files(self):
        for path in sorted(ROOT.rglob("*.xml")):
            if "target" in path.parts or ".venv" in path.parts:
                continue
            yield path

    def test_every_policy_file_parses(self):
        for path in self._xml_files():
            try:
                ET.parse(path)
            except ET.ParseError as e:
                raise AssertionError("%s does not parse: %s" % (path, e))

    def test_no_comment_contains_a_double_hyphen(self):
        offenders = []
        for path in self._xml_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"<!--(.*?)-->", text, re.S):
                if "--" in match.group(1):
                    offenders.append("%s: %r"
                                     % (path.relative_to(ROOT),
                                        match.group(1)[:60]))
        assert offenders == [], (
            "a double hyphen inside a comment makes the file unparseable:\n  "
            + "\n  ".join(offenders))
