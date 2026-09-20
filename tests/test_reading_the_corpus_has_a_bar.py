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
"""Reading the corpus gets a bar, not a wall of log.

Everything the run marker reports is counted off the disk, because a
directory cannot drift from itself. The extract has nothing to count: no
chunk exists until the whole 38GB has been read, so chunksTotal is 0 for
the longest stage of the run. Gloss asks `Number(chunksTotal) > 0` before
it draws anything, so that stage always failed the test and always showed
the tail of the log where the bar belongs.

The files read are the progress, and the extract already knows them -- it
was printing them to a log and nowhere a pane could draw them.
"""

import json
import subprocess
import sys

from conftest import BIN

MARKER = BIN / "bt-run-marker"
EXTRACT = (BIN / "bt-extract-strings").read_text()


def marker_run(home, *args):
    out = subprocess.run([sys.executable, str(MARKER)] + list(args),
                         capture_output=True, text=True,
                         env={"BIGTRANSLATE_HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    return json.loads((home / "data" / "run").read_text())


def home_with_dirs(tmp_path):
    for d in ("strings", "translated", "translated-catalog"):
        (tmp_path / "data" / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestTheMarkerCarriesTheReadPosition:

    def test_a_beat_records_how_far_the_read_has_got(self, tmp_path):
        home = home_with_dirs(tmp_path)
        marker_run(home, "start", "--path", "/corpus")
        state = marker_run(home, "beat", "--files-done", "1400",
                           "--files-total", "2806")
        assert state["stage"] == "extracting"
        assert state["filesDone"] == 1400
        assert state["filesTotal"] == 2806

    def test_a_plain_beat_keeps_the_position(self, tmp_path):
        # Other things beat the marker too. None of them should erase the
        # only progress the extract has.
        home = home_with_dirs(tmp_path)
        marker_run(home, "start", "--path", "/corpus")
        marker_run(home, "beat", "--files-done", "1400", "--files-total", "2806")
        state = marker_run(home, "beat")
        assert state["filesDone"] == 1400

    def test_the_position_goes_away_once_there_are_chunks(self, tmp_path):
        # The handover: a chunk exists, so the stage is translating and the
        # bar should measure chunks. A stale file count left behind would
        # make it measure the wrong thing for the rest of the run.
        home = home_with_dirs(tmp_path)
        marker_run(home, "start", "--path", "/corpus")
        marker_run(home, "beat", "--files-done", "1400", "--files-total", "2806")
        (home / "data" / "strings" / "chunk-00000.json").write_text("{}")
        state = marker_run(home, "beat")
        assert state["stage"] == "translating"
        assert "filesDone" not in state
        assert state["chunksTotal"] == 1


class TestTheExtractReportsIt:

    def test_the_beat_is_given_the_position(self):
        assert "beat(number, len(paths))" in EXTRACT

    def test_the_beat_passes_it_to_the_marker(self):
        assert '"--files-done"' in EXTRACT
        assert '"--files-total"' in EXTRACT

    def test_saying_so_never_costs_the_read(self):
        # A corpus read is forty minutes. Nothing about reporting on it is
        # worth losing that.
        assert "could not refresh the run marker" in EXTRACT
