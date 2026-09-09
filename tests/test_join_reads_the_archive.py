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
"""The join has to read every node's output, not just the manager's.

A translate task writes its chunk into the flat translated directory on
whatever machine ran it. The join runs on the manager and read that same flat
directory, so it only ever saw the chunks the manager itself had translated.

On a two node run the manager's flat directory held 9 of 62 chunks and the
other 53 were on the compute node. The join would have built its translation
database from a seventh of the corpus, indexed that, and reported success --
the rest of the corpus silently left in Spanish.

Remote data transfer brings every node's output back to the File Manager
archive, so the archive is the only copy that is complete. It is laid out by
BasicVersioner as <name>/<name> rather than flat, which is why the readers
have to understand both shapes.
"""
import importlib.machinery
import importlib.util
import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
TASKS = ROOT / "workflow" / "src" / "main" / "resources" / "policy" / "tasks.xml"


def load(name):
    """These are commands, not modules: no .py suffix to import by."""
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(
            name.replace("-", "_"), str(BIN / name)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_flat(directory, name, pairs):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(pairs), encoding="utf-8")


def write_archived(directory, name, pairs):
    """The shape BasicVersioner produces: <name>/<name>."""
    holder = directory / name
    holder.mkdir(parents=True, exist_ok=True)
    (holder / name).write_text(json.dumps(pairs), encoding="utf-8")


class TestChunksAreFoundInEitherLayout:

    def test_a_flat_directory_still_works(self, tmp_path):
        # A single machine deployment, where the flat directory is complete.
        write_flat(tmp_path, "chunk-00000.json", {"hola": "hello"})
        write_flat(tmp_path, "chunk-00001.json", {"adios": "goodbye"})
        joiner = load("bt-join-index")
        assert len(joiner.chunk_files(tmp_path.as_posix())) == 2
        assert joiner.count_chunks(tmp_path.as_posix()) == 2

    def test_the_archive_layout_is_found(self, tmp_path):
        write_archived(tmp_path, "chunk-00000.json", {"hola": "hello"})
        write_archived(tmp_path, "chunk-00001.json", {"adios": "goodbye"})
        joiner = load("bt-join-index")
        found = joiner.chunk_files(tmp_path.as_posix())
        assert len(found) == 2, (
            "an archived chunk is a file inside a directory of the same name; "
            "globbing the directory alone finds nothing to read")
        for path in found:
            assert Path(path).is_file()

    def test_the_holding_directory_is_not_counted_as_a_chunk(self, tmp_path):
        # It matches chunk-*.json too, and counting it would report a chunk
        # that cannot be opened.
        write_archived(tmp_path, "chunk-00000.json", {"hola": "hello"})
        joiner = load("bt-join-index")
        found = joiner.chunk_files(tmp_path.as_posix())
        assert len(found) == 1
        assert Path(found[0]).name == "chunk-00000.json"
        assert Path(found[0]).parent.name == "chunk-00000.json"

    def test_a_mixed_directory_finds_both_and_does_not_double_count(
            self, tmp_path):
        write_flat(tmp_path, "chunk-00000.json", {"hola": "hello"})
        write_archived(tmp_path, "chunk-00001.json", {"adios": "goodbye"})
        joiner = load("bt-join-index")
        assert joiner.count_chunks(tmp_path.as_posix()) == 2

    def test_an_empty_directory_counts_nothing(self, tmp_path):
        joiner = load("bt-join-index")
        assert joiner.count_chunks(tmp_path.as_posix()) == 0


class TestTheDatabaseIsBuiltFromTheArchive:

    def test_every_archived_chunk_reaches_the_database(self, tmp_path):
        # The failure this prevents: a database built from the manager's share
        # of the chunks, which the join then indexes and calls done.
        archive = tmp_path / "translated-catalog"
        for n in range(62):
            write_archived(archive, "chunk-%05d.json" % n,
                           {"origen-%d" % n: "source-%d" % n})

        builder = load("bt-build-translation-db")
        out = tmp_path / "translations.sqlite"
        chunks, total = builder.build(archive.as_posix(), out.as_posix())

        assert chunks == 62
        assert total == 62
        conn = sqlite3.connect(out.as_posix())
        try:
            rows = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
            assert rows == 62
            assert conn.execute(
                "SELECT e FROM t WHERE s = ?", ("origen-61",)
            ).fetchone()[0] == "source-61"
        finally:
            conn.close()


class TestThePolicyPointsTheJoinAtTheArchive:

    def _task(self, task_id):
        root = ET.parse(TASKS).getroot()
        for task in root.iter("task"):
            if task.get("id") == task_id:
                return {p.get("name"): p.get("value")
                        for p in task.iter("property")}
        raise AssertionError("no task %s" % task_id)

    def test_the_join_reads_the_archive(self):
        props = self._task("urn:bigtranslate:Join_Index_Task")
        assert props["TranslatedDir"].endswith("/data/translated-catalog"), (
            "the flat directory holds only what this machine translated")

    def test_a_translate_task_still_writes_to_the_flat_directory(self):
        # It is the node's own output directory, and the File Manager ingests
        # from there. Only the join's input moves.
        props = self._task("urn:bigtranslate:Translate_Chunk_Task")
        assert props["TranslatedDir"].endswith("/data/translated")
