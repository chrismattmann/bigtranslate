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
"""`bigtranslate translate` has to start the pipeline it says it is running.

EmploymentCorpusReady starts the extract, and it appeared exactly once in
the entire deployment: in the declaration naming the workflow it starts.
Nothing sent it. Every run of the three stage pipeline this project is
built around was started by a person sending the event by hand, and a run
where nobody did looked like this:

    2026-09-11 18:30:01 Crawl finished; the workflow manager is translating.
    2026-09-11 18:30:47 Translating: 172 workflow instances still running (0s)
    2026-09-11 18:32:49 Workflow finished after 30s.

Exit 0, nothing extracted, nothing translated, nothing indexed. The 172
instances were the per-file W1 split workflows, which fail immediately
because they name a queue the deployment does not define, and a stage that
fails fast drains fast.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
DRIVER = BIN / "bigtranslate"
EVENTS = (ROOT / "workflow" / "src" / "main" / "resources" / "policy"
          / "events.xml")

BODY = DRIVER.read_text()


def test_the_event_still_names_the_extract_workflow():
    # If this ever stops being true the driver is sending the wrong thing.
    events = EVENTS.read_text()
    block = re.search(
        r'<event\s+name="EmploymentCorpusReady".*?</event>', events, re.S)
    assert block, "EmploymentCorpusReady is not declared"
    assert "ExtractStringsWorkflow" in block.group(0)


def test_translate_sends_the_event():
    assert "EmploymentCorpusReady" in BODY, (
        "bigtranslate translate never starts the extract, so a run crawls "
        "and then reports success having translated nothing")


def test_it_is_sent_after_the_crawl_and_before_the_wait():
    # The extract reads the catalogue, so it must not start while files are
    # still arriving; and the wait must cover it, or the run is unsupervised.
    lines = BODY.splitlines()

    def line_of(needle, after=0):
        for i, line in enumerate(lines):
            if i >= after and needle in line:
                return i
        raise AssertionError("not found in bigtranslate: " + needle)

    crawl = line_of("crawler_launcher")
    done = line_of('say "Crawl finished', crawl)
    call = line_of("start_the_pipeline;", done)
    wait = line_of("    wait_for_workflow", call)
    assert crawl < done < call < wait, (
        "the extract is not started between the crawl and the wait")
    # And the send itself is in the helper, not inlined somewhere else.
    assert "--eventName EmploymentCorpusReady" in BODY


def test_a_refused_event_is_not_a_successful_run():
    # The whole failure this fixes is a run that reports success having done
    # nothing, so failing to start must not fall through into the wait.
    start = BODY.index("start_the_pipeline() {")
    end = BODY.index("running_instance_count() {")
    helper = BODY[start:end]
    assert "return 1" in helper, "a refused event is not reported as failure"
    assert "Nothing will be translated" in helper


def test_the_run_is_not_called_over_on_a_between_stage_gap():
    # Two polls was enough when the wait only covered the W1 instances, which
    # are made by the crawl and then only finish. Waiting on the three stage
    # pipeline means the quiet moments are between stages.
    assert "TRANSLATE_SETTLE" in BODY
    settle = int(re.search(r'TRANSLATE_SETTLE=\$\{TRANSLATE_SETTLE:-(\d+)\}',
                           BODY).group(1))
    poll = int(re.search(r'TRANSLATE_POLL=\$\{TRANSLATE_POLL:-(\d+)\}',
                         BODY).group(1))
    assert settle >= 4 * poll, (
        "a %ds settle over a %ds poll is too few quiet polls to tell a gap "
        "between stages from the end of a run" % (settle, poll))
