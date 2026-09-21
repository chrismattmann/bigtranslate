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
"""Chunks are equal in count and unequal in work.

The extract sorts every distinct string by length before cutting chunks, so
the first holds 5,000 strings averaging four characters and the last holds
paragraphs averaging 254 -- a 64x spread in what a chunk costs to translate.

On the run this was written against, chunks happened to finish evenly
across that range, so counting them landed within two points of the truth.
That is luck, not construction: the scheduler dispatches chunks as nodes
free up, and anything that makes completion uneven -- one slow node holding
the long chunks, a resumed run, a node joining late -- pulls the two apart.
Weighted, 240 of 458 is 50%; if those 240 had been the short ones it would
be 29%, and the estimate built on it would be out by a factor of two.
"""

import json
import os

from conftest import BIN

EXTRACT = (BIN / "bt-extract-strings").read_text()


def load_marker():
    """bt-run-marker's helpers, without running its main()."""
    source = (BIN / "bt-run-marker").read_text().split("def main(")[0]
    namespace = {}
    exec(compile(source, "bt-run-marker", "exec"), namespace)
    return namespace


def write_manifest(home, entries):
    out = home / "data" / "jobs" / "extract" / "1789" / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({"chunks": entries}))


class TestTheExtractRecordsTheCost:

    def test_the_manifest_carries_characters(self):
        assert '"chars": sum(len(value) for value in piece)' in EXTRACT


class TestTheWeightsAreRead:

    def test_chars_are_used_when_present(self, tmp_path):
        ns = load_marker()
        write_manifest(tmp_path, [
            {"chunk": "chunk-00000.json", "count": 5000, "chars": 20000},
            {"chunk": "chunk-00001.json", "count": 5000, "chars": 900000},
        ])
        weights = ns["chunk_weights"](str(tmp_path))
        assert weights["chunk-00000.json"] == 20000
        assert weights["chunk-00001.json"] == 900000

    def test_an_older_manifest_falls_back_to_the_length_range(self, tmp_path):
        # A run that started before the extract recorded chars still gets a
        # usable weight: a chunk's strings are nearly all the same length,
        # which is the point of sorting them.
        ns = load_marker()
        write_manifest(tmp_path, [
            {"chunk": "chunk-00000.json", "count": 5000,
             "min_length": 1, "max_length": 5},
        ])
        weights = ns["chunk_weights"](str(tmp_path))
        assert weights["chunk-00000.json"] == 5000 * 3.0

    def test_no_manifest_is_no_weights_not_a_crash(self, tmp_path):
        ns = load_marker()
        assert ns["chunk_weights"](str(tmp_path)) == {}

    def test_unreadable_manifest_is_no_weights_not_a_crash(self, tmp_path):
        ns = load_marker()
        out = tmp_path / "data" / "jobs" / "extract" / "1789" / "output"
        out.mkdir(parents=True)
        (out / "manifest.json").write_text("{ not json")
        assert ns["chunk_weights"](str(tmp_path)) == {}


class TestProgressReportsBoth:

    def test_weight_done_counts_only_finished_chunks(self, tmp_path):
        ns = load_marker()
        for d in ("strings", "translated", "translated-catalog"):
            (tmp_path / "data" / d).mkdir(parents=True)
        for n in range(3):
            (tmp_path / "data" / "strings" / ("chunk-%05d.json" % n)).write_text("[]")
        # Only the cheap one is finished.
        (tmp_path / "data" / "translated" / "chunk-00000.json").write_text("{}")
        write_manifest(tmp_path, [
            {"chunk": "chunk-00000.json", "count": 1, "chars": 20000},
            {"chunk": "chunk-00001.json", "count": 1, "chars": 900000},
            {"chunk": "chunk-00002.json", "count": 1, "chars": 900000},
        ])
        state = ns["progress"](str(tmp_path))
        assert state["chunksDone"] == 1 and state["chunksTotal"] == 3
        assert state["weightDone"] == 20000
        assert state["weightTotal"] == 1820000
        # One chunk of three is 33%; one twentieth of the text is 1%.
        assert round(100 * state["weightDone"] / state["weightTotal"]) == 1
