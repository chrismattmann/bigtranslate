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

METOUT = POLICY / "metout"
TASKS = WORKFLOW_POLICY / "tasks.xml"
POLICY_DIR = WORKFLOW_POLICY


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

    @pytest.mark.parametrize("name", ["PgeConfig_ExtractStrings.xml",
                                      "PgeConfig_TranslateChunk.xml",
                                      "PgeConfig_JoinIndex.xml"])
    def test_pge_config_carries_no_ext_dirs(self, name):
        assert "java.ext.dirs" not in (POLICY / "no_filter" / name).read_text()


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

    def test_avro_request_timeout_is_exported(self):
        text = (BIN / "setenv.sh").read_text()
        assert "org.apache.oodt.avro.client.requestTimeoutMillis" in text

    def test_opsui_overlay_is_vue_not_wicket(self):
        web = (REPO / "webapps/opsui/src/main/webapp/WEB-INF/web.xml").read_text()
        assert "index.html" in web
        assert "WicketFilter" not in web
        assert "OpsuiApp" not in web
        ctx = (REPO / "webapps/opsui/src/main/webapp/META-INF/context.xml").read_text()
        assert "opsui.skin" not in ctx
        assert "ganglia.url" not in ctx

    def test_pcs_ll_conf_filename_is_not_typoed(self):
        ctx = (REPO / "webapps/pcs-services/src/main/webapp/META-INF/context.xml").read_text()
        assert "pcs-ll-conf.xml" in ctx
        assert "pcs-ll-conf.xmnl" not in ctx

    def test_workflow_cli_spring_paths_are_runtime_urls(self):
        text = (REPO / "workflow/src/main/resources/etc/workflow.properties").read_text()
        assert "file://[WORKFLOW_HOME]/policy/cmd-line-actions.xml" in text
        assert "src/main/resources/cmd-line-actions.xml" not in text

    def test_no_curator_or_docker_overlay(self):
        names = [p.name.lower() for p in REPO.rglob("*")
                 if "/target/" not in str(p) and "/.git/" not in str(p)
                 and p.is_file()]
        assert not any("curator" in n for n in names)
        assert "docker-compose.yml" not in names

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


class TestRetiredTooling:
    """Things the pipeline used to need and must not quietly come back."""

    def test_tika_server_classpath_is_retired(self):
        text = (BIN / "setenv.sh").read_text()
        assert "TIKA_SERVER_CLASSPATH" not in text

    def test_the_w1_pipeline_is_gone(self):
        # One task per TSV, translating every row of every file. Superseded
        # by the extract/translate/join pipeline, which deduplicates globally
        # first: 836 million model calls became 2.3 million. It stayed wired
        # to the crawler long after nothing used it, and because its tasks
        # named no queue every one of them failed on submission -- 11,232
        # failed instances in a single run, which is most of what the failure
        # count reported.
        for name in ("Split.workflow.xml", "BigTranslate.workflow.xml"):
            assert not (POLICY_DIR / name).exists(), "%s is back" % name
        for name in ("PgeConfig_Split.xml", "PgeConfig_BigTranslate.xml"):
            assert not (POLICY / "no_filter" / name).exists(), "%s is back" % name
        tasks = TASKS.read_text()
        for task in ("Split_Task", "BigTranslate_Task", "FilterTask"):
            assert task not in tasks, "%s is back in tasks.xml" % task
        events = (POLICY_DIR / "events.xml").read_text()
        for event in ("EmploymentJobAggregatesTsvIngest",
                      "EmploymentJobAggregatesTsvSplitIngest"):
            assert event not in events, "%s is back in events.xml" % event

    def test_the_corpus_crawl_fires_no_per_file_event(self):
        # TriggerPostIngestWorkflow fires [ProductType]Ingest, which for the
        # corpus crawl is EmploymentJobAggregatesTsvIngest -- W1's trigger.
        # The extract keeps its own, because EmploymentStringChunkIngest is
        # what gives each chunk a translate workflow.
        driver = (BIN / "bigtranslate").read_text()
        crawl = driver[driver.index("crawler_launcher"):]
        crawl = crawl[:crawl.index("productPath")]
        assert "--actionIds" not in crawl, (
            "the corpus crawl still fires a per-file workflow event")
        extract = (POLICY / "no_filter" / "PgeConfig_ExtractStrings.xml").read_text()
        assert "TriggerPostIngestWorkflow" in extract, (
            "the extract must still trigger the chunk ingest event")


class TestEveryTaskConfigShips:
    """A task naming a conf file that is not there fails at run time.

    Was the BigTranslate_Task's properties; now every task, because the
    check was never specific to that one and W2 has three tasks referencing
    four conf files between them.
    """

    def test_every_referenced_conf_file_ships(self):
        root = ET.parse(TASKS).getroot()
        missing = []
        for task in root.iter("task"):
            for prop in task.iter("property"):
                value = prop.get("value") or ""
                if "/conf/" not in value:
                    continue
                name = value.rsplit("/", 1)[-1]
                if not (CONF / name).is_file():
                    missing.append("%s -> %s" % (task.get("name"), name))
        assert not missing, "conf files named but not shipped: " + ", ".join(missing)

    def test_the_translate_task_still_declares_its_batch_size(self):
        root = ET.parse(TASKS).getroot()
        for task in root.iter("task"):
            if task.get("name") == "Translate_Chunk_Task":
                names = {p.get("name") for p in task.iter("property")}
                assert "TranslateBatchSize" in names
                return
        raise AssertionError("no Translate_Chunk_Task in tasks.xml")


class TestCorpusConfig:
    def test_column_headers_match_the_corpus_width(self):
        # The computrabajo TSVs parse to exactly 20 tab-separated fields.
        cols = [c for c in (CONF / "colheaders.txt").read_text().splitlines() if c.strip()]
        assert len(cols) == 20

    @staticmethod
    def _columns(name):
        """The same reading the tools do: blank lines and # comments skipped."""
        return [c.strip() for c in (CONF / name).read_text().splitlines()
                if c.strip() and not c.lstrip().startswith("#")]

    def test_translate_columns_all_exist_in_the_header_list(self):
        headers = set(self._columns("colheaders.txt"))
        targets = self._columns("translate.cols")
        assert targets
        for col in targets:
            assert col in headers, "%r is not a known column" % col

    def test_place_name_columns_are_never_translated(self):
        """The model translates proper nouns, and it does it confidently.

            Lima             -> Five             20,318,816 documents
            Antioquia        -> Antioch           3,757,343 documents
            Valle            -> Valais            (a Swiss canton)
            Capital Federal  -> Federal Capital
            Santiago         -> SANTIAGO

        "Lima" became the number five and was the largest department value in
        the index. Every geographic question asked of this corpus groups by
        these, so they are the one thing that has to survive unchanged.
        """
        targets = set(self._columns("translate.cols"))
        for col in ("department", "location"):
            assert col not in targets, (
                "%r holds place names and must not be translated" % col)

    def test_the_tools_read_this_file_the_same_way(self):
        """Extract decides what is collected; join decides what is put back.

        A file the two read differently translates a column nobody
        substitutes, or substitutes one nobody translated.
        """
        import importlib.machinery
        import importlib.util

        def load(name):
            path = BIN / name
            spec = importlib.util.spec_from_loader(
                name, importlib.machinery.SourceFileLoader(name, str(path)))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        path = str(CONF / "translate.cols")
        extract = load("bt-extract-strings").read_columns(path)
        join = load("bt-join-index").read_columns(path)
        assert extract == join
        assert extract == self._columns("translate.cols")
        # And a comment is a comment, not a column named "# ...".
        assert not any(c.startswith("#") for c in extract)

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
        # The script still points people at Gloss, but by the port the
        # deployment was started on rather than the literal 8080: that
        # default belongs to whatever OODT stack came first on a machine
        # running more than one. See tests/test_port_isolation.py.
        assert "/gloss/" in text
        assert "${TOMCAT_PORT}/gloss/" in text

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


def test_no_xml_comment_contains_a_double_hyphen():
    """"--" is illegal inside an XML comment, and the parser says only that.

    Four separate times in this work a comment explaining something used a
    dash pair for punctuation, or named a command line flag, and the file
    stopped parsing with a column number and no hint of the cause.
    """
    import glob
    import re
    offenders = []
    for path in glob.glob(str(REPO / "**" / "*.xml"), recursive=True):
        if "/target/" in path or "node_modules" in path:
            continue
        try:
            source = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for match in re.finditer(r"<!--(.*?)-->", source, re.S):
            if "--" in match.group(1):
                offenders.append("%s: %s"
                                 % (path.replace(str(REPO) + "/", ""),
                                    match.group(1).strip()[:70]))
    assert not offenders, (
        "XML comments cannot contain '--':\n  " + "\n  ".join(offenders[:8]))

def test_solr_gets_a_heap_a_full_run_can_use():
    """Solr's own default is 512m.

    Ample for a test run's tens of thousands of documents, and not what
    this corpus asks for: the employment set indexes 119,453,210 documents
    into an 88GB index, and the merging that goes with it is where a small
    heap stops being survivable.
    """
    env = (REPO / "distribution" / "src" / "main" / "resources"
           / "bin" / "setenv.sh").read_text()
    assert "export SOLR_HEAP=${SOLR_HEAP:-" in env, "the heap is not settable"
    oodt = (REPO / "distribution" / "src" / "main" / "resources"
            / "bin" / "oodt").read_text()
    assert "SOLR_JAVA_MEM=" in oodt and "$SOLR_HEAP" in oodt, (
        "SOLR_HEAP is declared but never reaches Solr")


def test_an_index_off_the_deployment_is_told_through_data_home():
    """Not through a dataDir in core.properties.

    Solr runs under a security manager whose policy grants file access to
    ${solr.data.home} and its children by name. A core pointed anywhere
    else fails to load with an AccessControlException naming a file inside
    the directory it was just told to use.
    """
    oodt = (REPO / "distribution" / "src" / "main" / "resources"
            / "bin" / "oodt").read_text()
    assert "-Dsolr.data.home=" in oodt, (
        "the index location never reaches Solr's security policy")
    assert "SOLR_DATA_DIR" in oodt
    env = (REPO / "distribution" / "src" / "main" / "resources"
           / "bin" / "setenv.sh").read_text()
    assert "export SOLR_DATA_DIR=${SOLR_DATA_DIR:-}" in env, (
        "the index location cannot be set per deployment")


def test_every_product_type_a_task_writes_is_declared():
    """A task naming an undeclared type fails only when it runs.

    The failure is "Unknown product type: EmploymentStringChunk" from the
    catalog, thrown while the PGE builds its config, several layers away
    from the tasks.xml line that named it.
    """
    import re
    import xml.etree.ElementTree as ET
    tasks = (WORKFLOW_POLICY / "tasks.xml").read_text()
    named = set(re.findall(r'<property name="ProductType" value="([^"]+)"',
                           tasks))
    assert named, "no task declares a ProductType"
    types = REPO / "filemgr" / "src" / "main" / "resources" / "policy"
    declared = set()
    for path in types.rglob("product-types.xml"):
        for node in ET.parse(path).getroot().iter("type"):
            if node.get("name"):
                declared.add(node.get("name"))
    missing = sorted(named - declared)
    assert not missing, (
        "tasks.xml names product types the file manager does not declare: %s"
        % missing)


def test_every_declared_product_type_is_in_the_element_map():
    import xml.etree.ElementTree as ET
    policy = (REPO / "filemgr" / "src" / "main" / "resources" / "policy"
              / "bigtranslate")
    ids = {n.get("id") for n in
           ET.parse(policy / "product-types.xml").getroot().iter("type")
           if n.get("id")}
    mapped = {n.get("id") for n in
              ET.parse(policy / "product-type-element-map.xml").getroot()
              .iter("type") if n.get("id")}
    missing = sorted(ids - mapped)
    assert not missing, "product types absent from the element map: %s" % missing


def test_the_deployment_finds_itself():
    """setenv.sh must not assume where it was installed.

    The default was /usr/local/bigtranslate, so a deployment unpacked
    anywhere else worked only if the caller exported BIGTRANSLATE_HOME
    first. bin/oodt does, which is why the servers were fine and only the
    client scripts fell over:

      ./filemgr-client --url ... --operation --getNumProducts
      cd: /usr/local/bigtranslate/filemgr/bin: No such file or directory
      ClassNotFoundException: ...FileManagerClientMain

    which reads like a broken install rather than an unset variable.
    """
    env = (REPO / "distribution" / "src" / "main" / "resources"
           / "bin" / "setenv.sh").read_text()
    assert "BASH_SOURCE" in env, (
        "setenv.sh does not work out where it is; a deployment outside "
        "/usr/local/bigtranslate will not find its own jars")
    assert "_bt_bin" in env


def test_the_derived_home_is_the_directory_above_bin(tmp_path):
    """Exercised, not asserted about: source it from elsewhere and look."""
    import subprocess
    home = tmp_path / "somewhere" / "else"
    (home / "bin").mkdir(parents=True)
    source = (REPO / "distribution" / "src" / "main" / "resources"
              / "bin" / "setenv.sh").read_text()
    # Only the block under test; the rest reaches for a live deployment.
    block = source[:source.index("# Ports first")]
    (home / "bin" / "setenv.sh").write_text(block)
    result = subprocess.run(
        ["bash", "-c",
         'cd /tmp && unset BIGTRANSLATE_HOME && . "%s" && echo "$BIGTRANSLATE_HOME"'
         % (home / "bin" / "setenv.sh")],
        capture_output=True, text=True, timeout=60)
    got = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    assert got == str(home), (
        "sourced from /tmp it resolved to %r, wanted %r" % (got, str(home)))


def test_a_stale_pid_file_does_not_block_a_start():
    """A pid file whose process is gone is not a running service.

    It is what a crash or a kill -9 leaves behind. Treating its mere
    existence as "still running" means every later start refuses, with a
    message that sends you looking for a process that does not exist. The
    resource manager sat down for an hour this way.
    """
    launchers = [
        (REPO / "resmgr" / "src" / "main" / "resources" / "bin" / "resmgr"),
        (REPO / "workflow" / "src" / "main" / "resources" / "bin" / "wmgr"),
        (REPO / "filemgr" / "src" / "main" / "resources" / "bin" / "filemgr"),
    ]
    for path in launchers:
        source = path.read_text()
        assert "kill -0" in source, (
            "%s decides a service is running from a file rather than from "
            "the process" % path.name)
        assert "stale pid file" in source.lower(), (
            "%s does not clear a stale pid file" % path.name)


def test_the_stale_pid_guard_actually_works(tmp_path):
    """Exercised: a pid file naming a dead process must not stop a start."""
    import subprocess
    pid_file = tmp_path / "svc.pid"
    # A pid that has certainly exited: spawn one and wait for it.
    dead = subprocess.run(["bash", "-c", "echo $$"], capture_output=True,
                          text=True).stdout.strip()
    pid_file.write_text(dead)
    guard = '''
      RESMGR_PID="%s"
      if [ ! -z "$RESMGR_PID" ]; then
        if [ -f "$RESMGR_PID" ]; then
          _pid=`cat "$RESMGR_PID" 2>/dev/null`
          if [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null; then
            echo BLOCKED; exit 1
          fi
          rm -f "$RESMGR_PID"
        fi
      fi
      echo STARTED
    ''' % pid_file
    result = subprocess.run(["bash", "-c", guard], capture_output=True,
                            text=True, timeout=60)
    assert "STARTED" in result.stdout, (
        "a dead pid still blocked the start: %s" % result.stdout)
    assert not pid_file.exists(), "the stale file was not removed"
