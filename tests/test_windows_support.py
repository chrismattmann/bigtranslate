# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0.
"""Regression coverage for the Windows deployment path."""

import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "distribution" / "src" / "main" / "resources" / "bin"
POLICY = ROOT / "pge" / "src" / "main" / "resources" / "policy" / "no_filter"


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"),
                                                  str(BIN / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_launchers_ship():
    assert (BIN / "bigtranslate.ps1").is_file()
    assert (BIN / "oodt.ps1").is_file()


def test_pge_shells_resolve_bash_from_path():
    for path in POLICY.glob("PgeConfig_*.xml"):
        text = path.read_text(encoding="utf-8")
        assert 'shell="/bin/bash"' not in text


def test_corpus_is_per_run_workflow_metadata():
    driver = (BIN / "bigtranslate").read_text(encoding="utf-8")
    tasks = (ROOT / "workflow" / "src" / "main" / "resources" / "policy"
             / "tasks.xml").read_text(encoding="utf-8")
    assert '--key CorpusDir "$CORPUS_PATH"' in driver
    assert 'name="CorpusDir" value="[BIGTRANSLATE_CORPUS]"' not in tasks


def test_chunk_path_does_not_round_trip_through_sql():
    text = (POLICY / "PgeConfig_TranslateChunk.xml").read_text(encoding="utf-8")
    assert ('key="ChunkPath" '
            'val="[BIGTRANSLATE_HOME]/data/strings/[ChunkFile]/[ChunkFile]"'
            in text)


def test_each_successful_batch_refreshes_the_run_marker(monkeypatch):
    chunk = load("bt-translate-chunk")
    beats = []
    monkeypatch.setattr(chunk, "beat_run_marker", lambda: beats.append(True))

    class Translator:
        class ServiceUnavailable(Exception):
            pass

        def translate_batch(self, _url, batch, _beam, _length, _timeout):
            return ["en-" + value for value in batch]

    result = chunk.translate_chunk(Translator(), ["uno", "dos", "tres"],
                                   "http://127.0.0.1:8765", 2,
                                   1, 128, 30, 0, 0, "chunk.json")
    assert len(result) == 3
    assert len(beats) == 2


def test_the_powershell_version_gate_survives_a_pre_release():
    """[version]'1.0.0rc1' throws, and $ErrorActionPreference = 'Stop' means
    that ends the start rather than skipping a batching flag.

    A PEP 440 pre-release is a legal Python version and an illegal
    System.Version, so the installed version cannot be cast as it is read.
    Now that the required Pantogloss is 1.0.0rc1, every Windows start would
    have gone through that cast.
    """
    text = (BIN / "oodt.ps1").read_text(encoding="utf-8")
    assert "[version]($version" not in text, (
        "the reported version is cast straight to System.Version")
    assert "-match" in text, "nothing separates the release numbers out"
    assert "[version]::new(" in text, (
        "the version is not rebuilt from the matched numbers")


def test_the_windows_setup_floor_reaches_the_pre_release():
    """uv resolves a bare name to the newest *final* release.

    Which is the one that does not run here: below 1.0.0rc1 Pantogloss imports
    the Unix-only resource module. A constraint naming a pre-release admits
    pre-releases for that requirement, so the floor has to be in the specifier
    -- measured with uv 0.11.30, '>=0.19' resolves 0.25.0 and '>=1.0.0rc1'
    resolves 1.0.0rc1.
    """
    text = (BIN / "bigtranslate.ps1").read_text(encoding="utf-8")
    assert "'pantogloss[server]>=1.0.0rc1'" in text, (
        "the Windows setup floor does not name the pre-release, so uv "
        "installs a Pantogloss that cannot start on Windows")
