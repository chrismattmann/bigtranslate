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
"""The configuration that actually drives the pipeline.

Most of BigTranslate is policy XML, shell launchers and property files.
Gloss (webapps/gloss-services) is the Java that wraps those launchers for
the GUI. These tests guard the modernization work and the class of
regression that only shows up at runtime.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from conftest import BIN, CONF, POLICY, REPO, RESOURCES, WORKFLOW_POLICY

PGE_CONFIG = POLICY / "no_filter" / "PgeConfig_BigTranslate.xml"
SPLIT_CONFIG = POLICY / "no_filter" / "PgeConfig_Split.xml"
METOUT = POLICY / "metout"
TASKS = WORKFLOW_POLICY / "tasks.xml"


def xml_files():
    skip = ("/target/", "/.git/")
    return [p for p in REPO.rglob("*.xml")
            if not any(s in str(p) for s in skip)]


def launcher_scripts():
    names = ("filemgr", "filemgr-client", "query-tool", "wmgr", "wmgr-client",
             "resmgr", "resmgr-client", "batch_stub", "crawlctl",
             "crawler_launcher", "pcs_ll", "pcs_stat", "pcs_trace")
    return [p for p in REPO.rglob("src/main/resources/bin/*")
            if p.is_file() and p.name in names]


class TestXmlIsWellFormed:
    @pytest.mark.parametrize("path", xml_files(), ids=lambda p: p.name)
    def test_parses(self, path):
        ET.parse(path)


class TestJdk21Runtime:
    """Both flags were removed in Java 9 and fail at startup, not gradually."""

    @pytest.mark.parametrize("script", launcher_scripts(), ids=lambda p: p.name)
    def test_no_java_ext_dirs(self, script):
        assert "java.ext.dirs" not in script.read_text()

    @pytest.mark.parametrize("script", launcher_scripts(), ids=lambda p: p.name)
    def test_no_java_endorsed_dirs(self, script):
        assert "-Djava.endorsed.dirs" not in script.read_text()

    def test_pge_config_carries_no_ext_dirs(self):
        assert "java.ext.dirs" not in PGE_CONFIG.read_text()
        assert "java.ext.dirs" not in SPLIT_CONFIG.read_text()


class TestAvroTransport:
    """XML-RPC entry points no longer start a server under OODT 1.10."""

    @pytest.mark.parametrize(
        "script,expected",
        [
            ("filemgr", "FileManagerServerMain"),
            ("filemgr-client", "FileManagerClientMain"),
            ("wmgr", "WorkflowManagerStarter"),
            ("wmgr-client", "WorkflowManagerClientStarter"),
            ("resmgr", "ResourceManagerMain"),
        ],
    )
    def test_entry_point_is_current(self, script, expected):
        matches = [p for p in launcher_scripts() if p.name == script]
        assert matches, "launcher %s not found" % script
        assert expected in matches[0].read_text()

    def test_filemgr_declares_avro_factories(self):
        text = (REPO / "filemgr/src/main/resources/etc/filemgr.properties").read_text()
        assert "AvroFileManagerServerFactory" in text
        assert "AvroFileManagerClientFactory" in text

    def test_solr_catalog_profile_declares_avro_too(self):
        text = (REPO / "filemgr/src/main/resources/etc"
                       "/filemgr.fm-solr-catalog.properties").read_text()
        assert "AvroFileManagerServerFactory" in text

    def test_resmgr_declares_avro_transport(self):
        # The resource manager was the last part still speaking XML-RPC here,
        # and it named the transport in three separate places: the batch
        # manager factory, the batch stub launcher, and the client launcher.
        text = (REPO / "resmgr/src/main/resources/etc/resource.properties").read_text()
        assert "AvroRpcResourceManager" in text
        assert "AvroRpcResourceManagerClient" in text
        assert "AvroRpcBatchMgrFactory" in text

    def test_resmgr_scripts_do_not_name_xmlrpc(self):
        for name, expected in (("batch_stub", "AvroRpcBatchStub"),
                               ("resmgr-client", "ResourceManagerClientMain")):
            matches = [p for p in launcher_scripts() if p.name == name]
            assert matches, "launcher %s not found" % name
            text = matches[0].read_text()
            assert expected in text
            assert "XmlRpc" not in text

    def test_no_active_xmlrpc_selection_anywhere(self):
        # A commented-out XML-RPC option is fine; a live one is not. Apache
        # XML-RPC is being retired from Mnemosyne, and it is the last thing
        # keeping commons-httpclient 3.x and CVE-2012-5783 on the classpath.
        offenders = []
        for path in REPO.glob("*/src/main/resources/etc/*.properties"):
            for num, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or "=" not in stripped:
                    continue
                value = stripped.split("=", 1)[1]
                if "XmlRpc" in value:
                    offenders.append("%s:%d" % (path.name, num))
        assert not offenders, "XML-RPC still selected in: %s" % offenders

    def test_workflow_declares_avro_factories(self):
        text = (REPO / "workflow/src/main/resources/etc/workflow.properties").read_text()
        assert "AvroRpcWorkflowManagerFactory" in text

    def test_property_keys_are_not_corrupted(self):
        # Two keys carried stray xsorg./orxsg. prefixes from a 2016 edit, which
        # silently disabled both File Manager timeout settings.
        text = (REPO / "filemgr/src/main/resources/etc/filemgr.properties").read_text()
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0]
                assert not re.match(r"^(xs|orxs)", key), "corrupted key: %r" % key


class TestWorkflowExecution:
    def test_resource_manager_submission_stays_disabled(self):
        # With it enabled, instances sit in RSUBMIT unless nodes and queues are
        # provisioned, and the Split task never runs.
        text = (REPO / "workflow/src/main/resources/etc/workflow.properties").read_text()
        active = [l for l in text.splitlines()
                  if l.strip().startswith("org.apache.oodt.cas.workflow.engine"
                                          ".resourcemgr.url")]
        assert not active, "resourcemgr.url is enabled: %r" % active


class TestTranslateStep:
    def test_pge_invokes_the_pantogloss_shim(self):
        assert "pantogloss-translatejson" in PGE_CONFIG.read_text()

    def test_pge_no_longer_invokes_the_tika_backed_tool(self):
        text = PGE_CONFIG.read_text()
        assert not re.search(r"\btranslatejson\b(?!\s*\")", text.replace(
            "pantogloss-translatejson", ""))

    def test_translate_runs_once_per_directory(self):
        # One process per document would reload the model for every posting.
        text = PGE_CONFIG.read_text()
        assert "--in-dir" in text and "--out-dir" in text
        assert "xargs -I infile" not in text

    def test_shim_receives_the_glossary(self):
        assert "--glossary" in PGE_CONFIG.read_text()

    def test_poster_reads_the_translated_directory(self):
        text = PGE_CONFIG.read_text()
        assert re.search(r"find \[JobOutputDir\]/translated .*\| poster", text)

    def test_stamps_solr_lineage_before_poster(self):
        text = PGE_CONFIG.read_text()
        stamp = text.find("stamp-solr-lineage")
        poster = text.find("| poster")
        assert stamp != -1 and poster != -1 and stamp < poster


def _pge_output_dirs(path):
    root = ET.parse(path).getroot()
    output = root.find("output")
    assert output is not None, "%s has no <output>" % path
    return list(output.findall("dir"))


def _metout_keys(path):
    root = ET.parse(path).getroot()
    found = {}
    for node in root.findall("metadata"):
        found[node.get("key")] = node.get("val")
    return found


class TestBigTranslateIngest:
    """File Manager catalogs the TSV and the split; Solr holds the postings."""

    def test_split_still_writes_met_via_generic_metout(self):
        dirs = _pge_output_dirs(SPLIT_CONFIG)
        assert dirs
        files = dirs[0].find("files")
        assert files.get("metFileWriterClass").endswith("MetadataListPcsMetFileWriter")
        assert files.get("args").endswith("generic_metout.xml")

    def test_translate_does_not_ingest_leaf_json(self):
        dirs = _pge_output_dirs(PGE_CONFIG)
        paths = [d.get("path") for d in dirs]
        assert "[JobOutputDir]/employmentjobs" not in paths
        assert "[JobOutputDir]/translated" not in paths
        assert "[JobOutputDir]/aggregatejson" not in paths

    def test_does_not_delete_the_split_parent(self):
        text = PGE_CONFIG.read_text()
        assert "DeleteProduct" not in text
        assert "fmdel" not in text

    def test_wipes_working_copies_after_solr_post(self):
        text = PGE_CONFIG.read_text()
        poster = text.find("| poster")
        wipe = text.find("rm -rf [JobOutputDir]")
        assert poster != -1 and wipe != -1 and poster < wipe

    def test_lineage_keys_are_the_split_and_original_tsv(self):
        root = ET.parse(PGE_CONFIG).getroot()
        keys = {m.get("key"): m.get("val") for m in root.find("customMetadata").findall("metadata")}
        assert keys["SplitFilename"] == "[TsvFile]"
        assert keys["SourceTsv"] == "[InputFiles]"
        assert "[SplitFilename]" in PGE_CONFIG.read_text()
        assert "[SourceTsv]" in PGE_CONFIG.read_text()

    def test_tika_server_classpath_is_retired(self):
        text = (BIN / "setenv.sh").read_text()
        assert "TIKA_SERVER_CLASSPATH" not in text


@pytest.fixture(scope="module")
def properties():
    """Configuration properties of the BigTranslate_Task.

    The root element is namespaced but its children are not, so the task
    elements sit in no namespace.
    """
    root = ET.parse(TASKS).getroot()
    found = {}
    for task in root.iter("task"):
        if task.get("name") == "BigTranslate_Task":
            for prop in task.iter("property"):
                found[prop.get("name")] = prop.get("value")
    return found


class TestTaskProperties:
    def test_near_dupe_threshold_is_conservative(self, properties):
        # Direction is easy to read backwards: higher keeps more. At 0.1 the
        # filter discarded 206 of 211 rows on a sample country-day.
        assert float(properties["NearDupeThreshold"]) >= 0.7

    def test_cache_is_sqlite(self, properties):
        # rlite is unreachable: hirlite no longer builds.
        assert properties["TranslateCachePath"].endswith(".sqlite")

    def test_glossary_path_is_declared(self, properties):
        assert properties["TranslateGlossary"].endswith("glossary.es-en.tsv")

    def test_batch_size_is_positive(self, properties):
        assert int(properties["TranslateBatchSize"]) > 0

    def test_every_referenced_conf_file_ships(self, properties):
        for key in ("TranslateCols", "TranslateGlossary"):
            name = properties[key].rsplit("/", 1)[-1]
            assert (CONF / name).is_file(), "%s missing from conf/" % name


class TestCorpusConfig:
    def test_column_headers_match_the_corpus_width(self):
        # The computrabajo TSVs parse to exactly 20 tab-separated fields.
        cols = [c for c in (CONF / "colheaders.txt").read_text().splitlines() if c.strip()]
        assert len(cols) == 20

    def test_translate_columns_all_exist_in_the_header_list(self):
        headers = {c.strip() for c in
                   (CONF / "colheaders.txt").read_text().splitlines() if c.strip()}
        targets = [c.strip() for c in
                   (CONF / "translate.cols").read_text().splitlines() if c.strip()]
        assert targets
        for col in targets:
            assert col in headers, "%r is not a known column" % col

    def test_latin1_is_declared(self):
        # The corpus is not UTF-8: byte 0xe9 in "Mexico" aborts a strict read.
        encodings = [e.strip() for e in
                     (CONF / "encoding.txt").read_text().splitlines() if e.strip()]
        assert "latin-1" in encodings

    def test_encoding_file_has_no_mangled_entries(self):
        # Appending to a file with no trailing newline once produced
        # "us-asciilatin-1" as a single line.
        for line in (CONF / "encoding.txt").read_text().splitlines():
            if line.strip():
                assert " " not in line.strip()
                assert line.strip().count("-") <= 1 or line.strip() in ("latin-1", "us-ascii")


@pytest.fixture(scope="module")
def root_pom():
    return (REPO / "pom.xml").read_text()


class TestBuild:
    def test_targets_mnemosyne_release(self, root_pom):
        # Mnemosyne is the continuation of Apache OODT, which the ASF retired
        # to the Attic in April 2023. A release, not a SNAPSHOT, so the
        # coordinate cannot resolve to different bytes on different machines.
        assert "<oodt.version>1.11.0</oodt.version>" in root_pom

    def test_no_apache_oodt_coordinates_remain(self):
        # Java packages stay org.apache.oodt.*; only the Maven coordinate moved.
        # The 2020 org.apache.oodt:1.10-SNAPSHOT on Apache snapshots would
        # silently resolve in place of the fork if any pom still named it.
        stale = []
        for pom in REPO.rglob("pom.xml"):
            if "/target/" in str(pom):
                continue
            if "<groupId>org.apache.oodt</groupId>" in pom.read_text():
                stale.append(str(pom.relative_to(REPO)))
        assert not stale, "poms still on Apache coordinates: %s" % stale

    def test_oodt_dependencies_use_the_mnemosyne_group(self):
        found = False
        for pom in REPO.rglob("pom.xml"):
            if "/target/" in str(pom):
                continue
            if "<groupId>ai.mattmann.mnemosyne</groupId>" in pom.read_text():
                found = True
                break
        assert found, "no pom declares the Mnemosyne groupId"

    def test_no_plaintext_repositories(self, root_pom):
        assert "http://repository.apache.org" not in root_pom
        assert "http://download.java.net" not in root_pom

    def test_cas_pge_is_not_pinned_to_an_old_release(self):
        # pge/pom.xml pinned cas-pge to 0.3 while its siblings used the
        # property, so one module built against a different OODT.
        text = (REPO / "pge" / "pom.xml").read_text()
        match = re.search(
            r"<artifactId>cas-pge</artifactId>\s*<version>([^<]+)</version>", text)
        assert match and match.group(1) == "${oodt.version}"

    def test_tomcat_uses_current_coordinates(self):
        text = (REPO / "distribution" / "pom.xml").read_text()
        assert "<groupId>org.apache.tomcat</groupId>" in text
        assert "tomcat:apache-tomcat" not in text

    def test_solr_is_not_deployed_into_tomcat(self):
        # Solr runs as its own application now. The tests that used to live
        # here checked the war's web.xml for a JNDI solr/home entry that
        # overrode -Dsolr.solr.home; there is no war to check any more, and
        # nothing should put one back.
        assert not (REPO / "webapps/solr-webapp").exists()
        assert "solr-webapp" not in (REPO / "webapps/pom.xml").read_text()

    def test_oodt_starts_solr_against_the_deployment_solr_home(self):
        # The failure this replaces was Solr resolving its home relative to
        # Tomcat's working directory and finding no cores. It is now passed
        # explicitly.
        text = (BIN / "oodt").read_text()
        assert "solr-server" in text
        assert "--solr-home" in text

    def test_solr_home_ships_the_core(self):
        core = REPO / "solr/src/main/resources/bigtranslate"
        assert (core / "core.properties").exists()
        assert (core / "conf/solrconfig.xml").exists()
        assert (core / "conf/schema.xml").exists()

    def test_pcs_webapp_supplies_jaxb(self):
        # JAXB left the JDK in Java 11; CXFServlet fails to load without it.
        text = (REPO / "webapps/pcs-services/pom.xml").read_text()
        assert "jaxb-api" in text and "jaxb-runtime" in text

    def test_solr_is_reached_on_its_own_port(self):
        # Solr moved out of Tomcat, so nothing should still be pointing at
        # :8080/solr. Its own port is 8983.
        for rel in ("filemgr/src/main/resources/etc/filemgr.properties",
                    "filemgr/src/main/resources/etc/filemgr.fm-solr-catalog.properties",
                    "workflow/src/main/resources/policy/tasks.xml"):
            text = (REPO / rel).read_text()
            assert "8080/solr" not in text, rel

    def test_crawler_exclude_has_a_default(self):
        # Crawler precondition beans reference the placeholder, so invoking
        # crawler_launcher directly failed Spring context creation without it.
        assert "BIGTRANSLATE_EXCLUDE" in (BIN / "setenv.sh").read_text()

    def test_gloss_is_a_webapps_module(self):
        text = (REPO / "webapps/pom.xml").read_text()
        assert "<module>gloss</module>" in text
        assert "<module>gloss-services</module>" in text

    def test_distribution_unpacks_gloss_wars(self):
        text = (REPO / "distribution/pom.xml").read_text()
        assert "bigtranslate-gloss</artifactId>" in text
        assert "bigtranslate-gloss-services</artifactId>" in text
        assert "webapps/gloss</outputDirectory>" in text
        assert "webapps/gloss-services</outputDirectory>" in text

    def test_root_redirects_to_gloss(self):
        text = (REPO / "distribution/src/main/resources/tomcat/webapps/ROOT/index.jsp").read_text()
        assert "/gloss/" in text

    def test_cli_reset_accepts_yes(self):
        text = (BIN / "bigtranslate").read_text()
        assert "reset [--yes]" in text
        assert 'if [ "$1" = "--yes" ]' in text

    def test_cli_translate_still_exists_alongside_gloss(self):
        text = (BIN / "bigtranslate").read_text()
        assert "function translate" in text
        assert "8080/gloss" in text

    def test_gloss_services_expose_table_and_facets(self):
        text = (REPO / "webapps/gloss-services/src/main/java/org/bigtranslate/gloss/rest"
                       "/ServicesRestResource.java").read_text()
        assert '@Path("/table")' in text
        assert '@Path("/facets")' in text
        assert '@Path("/record")' in text


class TestShippedScripts:
    def test_shim_is_executable(self):
        path = BIN / "pantogloss-translatejson"
        assert path.is_file()
        assert path.stat().st_mode & 0o111, "shim must ship executable"
