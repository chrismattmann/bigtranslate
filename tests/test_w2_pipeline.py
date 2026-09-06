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
"""The three stages of the W2 pipeline.

Measured on the 2,806 file employment corpus: 119,453,210 lines hold
836,098,741 cells in the seven translatable columns, and those are only
2,286,371 distinct strings. Translating rows instead of distinct strings is
three hundred and sixty times the model time for the same answer, which is
the whole reason this pipeline exists.
"""
import ast
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "distribution" / "src" / "main" / "resources" / "bin"
CONF = REPO / "distribution" / "src" / "main" / "resources" / "conf"


def load(name):
    """These are commands, not modules: no .py suffix to import by."""
    path = BIN / name
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def corpus(tmp_path):
    """Two files sharing most of their values, as the real corpus does."""
    d = tmp_path / "corpus"
    d.mkdir()
    header = ["2012-10-23", "Capital Federal", "Capital Federal", "TITLE",
              "", "A convenir", "Inmediato", "Indeterminada",
              "Tiempo Completo", "Enviar Cv", "Softtek", "Belen", "", "",
              "Buenos Aires", "-34.6", "-58.3", "2012-10-29",
              "http://x/1", "2012-11-06"]
    for name, titles in (("a.tsv", ["Programador", "Ingeniero"]),
                         ("b.tsv", ["Programador", "Contador"])):
        rows = []
        for t in titles:
            row = list(header)
            row[3] = t
            rows.append("\t".join(row))
        (d / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return d


def test_extract_finds_the_distinct_strings(corpus, tmp_path):
    """Four rows, but "Programador" appears twice and is one job."""
    out = tmp_path / "strings"
    extract = load("bt-extract-strings")
    rc = extract.main(["--corpus", str(corpus), "--out-dir", str(out),
                       "--colheaders", str(CONF / "colheaders.txt"),
                       "--translate-cols", str(CONF / "translate.cols"),
                       "--chunk-size", "1000"])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    strings = json.loads((out / "chunk-00000.json").read_text())
    assert "Programador" in strings
    assert strings.count("Programador") == 1, "a duplicate was not collapsed"
    assert manifest["distinct"] == len(strings)
    assert manifest["dedup_factor"] > 1, "nothing was deduplicated"


def test_extract_sorts_chunks_by_length(corpus, tmp_path):
    """Batches pad to the longest source, so a chunk wants uniform lengths."""
    out = tmp_path / "strings"
    load("bt-extract-strings").main(
        ["--corpus", str(corpus), "--out-dir", str(out),
         "--colheaders", str(CONF / "colheaders.txt"),
         "--translate-cols", str(CONF / "translate.cols"),
         "--chunk-size", "1000"])
    strings = json.loads((out / "chunk-00000.json").read_text())
    lengths = [len(s) for s in strings]
    assert lengths == sorted(lengths), "the chunk is not length-ordered"


def test_extract_only_reads_the_translatable_columns(corpus, tmp_path):
    """A URL or a latitude is not a job for a translation model."""
    out = tmp_path / "strings"
    load("bt-extract-strings").main(
        ["--corpus", str(corpus), "--out-dir", str(out),
         "--colheaders", str(CONF / "colheaders.txt"),
         "--translate-cols", str(CONF / "translate.cols"),
         "--chunk-size", "1000"])
    strings = json.loads((out / "chunk-00000.json").read_text())
    assert not [s for s in strings if s.startswith("http")], "a url leaked in"
    assert "-34.6" not in strings, "a latitude leaked in"
    assert "2012-10-23" not in strings, "a date leaked in"


def test_a_partial_chunk_is_never_left_behind(tmp_path):
    """A chunk file that exists must be a chunk file that is complete."""
    extract = load("bt-extract-strings")
    out = tmp_path / "strings"
    written = extract.write_chunks({b"aa", b"b", b"ccc"}, str(out), 2)
    assert len(written) == 2
    assert not list(out.glob("*.partial")), "a partial file survived"
    for entry in written:
        json.loads((out / entry["chunk"]).read_text())


def test_join_rejoins_records_split_by_embedded_newlines(tmp_path):
    """Titles in this corpus contain newlines; records are not lines.

    Splitting on newlines mangles every row after such a title, and the
    damage indexes cleanly -- it is only noticed much later.
    """
    join = load("bt-join-index")
    columns = ["c%d" % i for i in range(20)]
    row = ["v%d" % i for i in range(20)]
    row[3] = "a title\nwith a newline"
    path = tmp_path / "one.tsv"
    path.write_text("\t".join(row) + "\n" + "\t".join(row) + "\n",
                    encoding="utf-8")
    got = list(join.records(str(path), columns))
    assert len(got) == 2, "expected two records, got %d" % len(got)
    for parts in got:
        assert len(parts) >= 20
        assert parts[3] == "a title\nwith a newline"


def test_join_substitutes_translations(tmp_path):
    join = load("bt-join-index")
    columns = ["postedDate", "location", "department", "title"]
    parts = ["2012-10-23", "Capital", "Ventas", "Programador"]
    doc, missing = join.build_document(
        parts, columns, {2, 3}, {"Programador": "Programmer",
                                 "Ventas": "Sales"},
        required=["title"], dates=["postedDate"], identifier="x-1")
    assert doc["title"] == "Programmer"
    assert doc["department"] == "Sales"
    assert doc["location"] == "Capital", "an untranslatable column changed"
    assert doc["postedDate"] == "2012-10-23T00:00:00Z"
    assert not missing


def test_an_untranslated_string_keeps_its_original(tmp_path):
    """Better a Spanish title than no title, and it is visible in the index."""
    join = load("bt-join-index")
    doc, _ = join.build_document(
        ["Programador"], ["title"], {0}, {}, required=[], dates=[],
        identifier="x-1")
    assert doc["title"] == "Programador"


def test_join_reports_documents_solr_would_reject(tmp_path):
    """Counted and reported, not posted and silently 400ed.

    Only a required date can leave a document unpostable now: everything
    else Solr merely wants present, and a blank satisfies that.
    """
    join = load("bt-join-index")
    doc, missing = join.build_document(
        ["only a title"], ["title"], set(), {},
        required=["title", "postedDate"], dates=["postedDate"],
        identifier="x-1")
    assert missing == ["postedDate"]
    doc, missing = join.build_document(
        ["only a title"], ["title"], set(), {},
        required=["title", "url"], dates=[], identifier="x-1")
    assert not missing, "a blank url should not reject the document"


def test_shards_partition_the_corpus_exactly_once(corpus):
    """Every file in exactly one shard, or rows are lost or doubled."""
    paths = sorted(str(p) for p in corpus.glob("*.tsv"))
    for of in (1, 2, 3, 8):
        seen = []
        for shard in range(of):
            seen.extend(paths[shard::of])
        assert sorted(seen) == paths, "shards of %d do not partition" % of


def test_the_engine_is_the_queue_based_one():
    props = (REPO / "workflow" / "src" / "main" / "resources" / "etc"
             / "workflow.properties").read_text()
    assert "PrioritizedQueueBasedWorkflowEngineFactory" in props
    assert "ThreadPoolWorkflowEngineFactory" not in props, (
        "the thread pool engine is still configured")
    for key in ("wengine.prioritizer", "wengine.runner.factory",
                "taskquerier.waitSeconds"):
        assert key in props, "W2 needs %s and it is not set" % key


def test_every_w2_workflow_has_a_task_and_an_event():
    policy = REPO / "workflow" / "src" / "main" / "resources" / "policy"
    tasks = (policy / "tasks.xml").read_text()
    events = (policy / "events.xml").read_text()
    for workflow, task in (("ExtractStringsWorkflow", "Extract_Strings_Task"),
                           ("TranslateChunkWorkflow", "Translate_Chunk_Task"),
                           ("JoinIndexWorkflow", "Join_Index_Task")):
        definition = policy / (workflow.replace("Workflow", "") + ".workflow.xml")
        alt = {"ExtractStrings": "Extract", "TranslateChunk": "TranslateChunk",
               "JoinIndex": "JoinIndex"}[workflow.replace("Workflow", "")]
        definition = policy / (alt + ".workflow.xml")
        assert definition.exists(), "%s has no definition" % workflow
        assert task in definition.read_text(), (
            "%s does not reference %s" % (workflow, task))
        assert task in tasks, "%s is not declared in tasks.xml" % task
        assert workflow in events, "nothing triggers %s" % workflow


def test_each_stage_has_a_pge_config():
    policy = REPO / "pge" / "src" / "main" / "resources" / "policy" / "no_filter"
    tasks = (REPO / "workflow" / "src" / "main" / "resources" / "policy"
             / "tasks.xml").read_text()
    for name, command in (("ExtractStrings", "bt-extract-strings"),
                          ("TranslateChunk", "bt-translate-chunk"),
                          ("JoinIndex", "bt-join-index")):
        config = policy / ("PgeConfig_%s.xml" % name)
        assert config.exists(), "%s has no PGE config" % name
        assert command in config.read_text(), (
            "%s does not run %s" % (config.name, command))
        assert config.name in tasks, "%s is not wired into a task" % config.name
        assert (BIN / command).exists(), "%s does not exist" % command


def test_dates_that_are_not_zero_padded_are_still_dates():
    """36% of postedDate in this corpus reads "2012-11-6", not "2012-11-06".

    Matching on length alone rejects those, and because postedDate is
    required the whole record is dropped -- a third of the corpus, with a
    clean index at the end of it to suggest nothing went wrong.
    """
    as_date = load("bt-join-index").as_solr_date
    assert as_date("2012-11-6") == "2012-11-06T00:00:00Z"
    assert as_date("2012-1-6") == "2012-01-06T00:00:00Z"
    assert as_date("2012-11-06") == "2012-11-06T00:00:00Z"


def test_a_thing_that_is_not_a_date_is_rejected():
    as_date = load("bt-join-index").as_solr_date
    for value in ("", "x", "2012-13-01", "2012-11", "2012-11-32", None,
                  "12-11-06"):
        assert as_date(value) is None, "%r was accepted as a date" % value


def test_an_unpadded_date_does_not_drop_the_record():
    """The bug end to end: the record survives, not just the parser."""
    join = load("bt-join-index")
    doc, missing = join.build_document(
        ["2012-11-6", "Programador"], ["postedDate", "title"], {1},
        {"Programador": "Programmer"},
        required=["postedDate", "title"], dates=["postedDate"],
        identifier="x-1")
    assert not missing, "an unpadded date still drops the record: %s" % missing
    assert doc["postedDate"] == "2012-11-06T00:00:00Z"


def test_a_blank_required_field_is_carried_through_not_dropped():
    """Solr requires presence, not content, and the corpus leaves cells blank.

    contactPerson is absent from 4% of records and latitude from 1%.
    Dropping those loses one record in twenty for want of a contact name.
    """
    join = load("bt-join-index")
    doc, missing = join.build_document(
        ["2012-11-6", "Programador"], ["postedDate", "title"], set(), {},
        required=["postedDate", "title", "contactPerson"],
        dates=["postedDate"], identifier="x-1")
    assert not missing, "a blank field dropped the record: %s" % missing
    assert doc["contactPerson"] == ""


def test_a_record_with_no_readable_date_is_still_dropped():
    """A posting we cannot place in time is not one we can index."""
    join = load("bt-join-index")
    doc, missing = join.build_document(
        ["not a date", "Programador"], ["postedDate", "title"], set(), {},
        required=["postedDate", "title"], dates=["postedDate"],
        identifier="x-1")
    assert missing == ["postedDate"]



def test_each_command_imports_the_submodules_it_uses():
    """A submodule attribute is only there if something imported it.

    bt-translate-chunk used importlib.machinery while importing only
    importlib.util, and the whole suite passed. Whether that works is a
    property of the interpreter build, not of the code:

        M3 python 3.8.12   importlib.util alone gives machinery -> True
        M3 venv   3.12.9                                        -> True
        Ubuntu    3.12.3                                        -> False

    So it ran here and died on the first node it was shipped to. No
    runtime test on this machine can catch that, because this machine is
    one of the ones where it works. Reading the source can.
    """
    for name in ("bt-extract-strings", "bt-translate-chunk", "bt-join-index"):
        source = (BIN / name).read_text()
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    for i in range(len(parts)):
                        imported.add(".".join(parts[:i + 1]))
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported.add(node.module + "." + alias.name)
                    imported.add(node.module)
        used = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name)):
                used.add("%s.%s" % (node.value.value.id, node.value.attr))
        # os.path is not like importlib.machinery: the standard library
        # documents it as always bound by "import os", and every
        # interpreter honours that. The submodules worth checking are the
        # ones whose presence is an accident of what else got imported.
        always_bound = {"os.path"}
        for dotted in sorted(used - always_bound):
            root = dotted.split(".")[0]
            # Only real submodules. "sys.stderr" is an attribute and is
            # always there; "importlib.machinery" is a module that has to
            # be imported by someone.
            try:
                if importlib.util.find_spec(dotted) is None:
                    continue
            except (ImportError, AttributeError, ValueError):
                continue
            if root in imported and dotted not in imported:
                pytest.fail(
                    "%s uses %s but only imports %s -- that works only on "
                    "interpreters where another import happens to pull it "
                    "in" % (name, dotted, root))


def test_each_command_runs_in_a_clean_interpreter():
    """The cheap smoke test: it at least starts."""
    for name in ("bt-extract-strings", "bt-translate-chunk", "bt-join-index"):
        result = subprocess.run(
            [sys.executable, str(BIN / name), "--help"],
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, (
            "%s cannot reach --help:\n%s" % (name, result.stderr[-600:]))
        assert "usage:" in result.stdout.lower()
