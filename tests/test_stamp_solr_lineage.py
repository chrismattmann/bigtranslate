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
"""Lineage fields stamped onto translated JSON before Solr post."""

import importlib.machinery
import importlib.util
import json
import os

from conftest import BIN

_spec = importlib.util.spec_from_loader(
    "stamp_solr_lineage",
    importlib.machinery.SourceFileLoader("stamp_solr_lineage", str(BIN / "stamp-solr-lineage")),
)
stamp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stamp)


def test_stamp_document_sets_the_three_lineage_fields():
    doc = stamp.stamp_document(
        {"id": "abc", "title": "Dev"},
        "file.tsv.aaaa", "file.tsv.aaaa", "file.tsv")
    assert doc["InputFiles"] == "file.tsv.aaaa"
    assert doc["SplitFilename"] == "file.tsv.aaaa"
    assert doc["TsvFile"] == "file.tsv"
    assert doc["id"] == "abc"


def test_stamp_document_skips_empty_values():
    doc = stamp.stamp_document({"id": "abc"}, "", "", "")
    assert "InputFiles" not in doc
    assert "SplitFilename" not in doc
    assert "TsvFile" not in doc


def test_stamp_dir_rewrites_json_files(tmp_path):
    path = tmp_path / "job.json"
    path.write_text('{"id": "1", "title": "X"}', encoding="utf-8")
    n = stamp.stamp_dir(str(tmp_path), "split.aaaa", "split.aaaa", "orig.tsv")
    assert n == 1
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["TsvFile"] == "orig.tsv"
    assert body["SplitFilename"] == "split.aaaa"


def test_script_is_executable():
    assert os.access(BIN / "stamp-solr-lineage", os.X_OK)
