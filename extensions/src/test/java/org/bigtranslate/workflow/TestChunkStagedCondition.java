/*
 * Licensed to the Apache Software Foundation (ASF) under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The ASF licenses this file to You under the Apache License, Version 2.0
 * (the "License"); you may not use this file except in compliance with
 * the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.bigtranslate.workflow;

import org.apache.oodt.cas.metadata.Metadata;
import org.apache.oodt.cas.workflow.structs.WorkflowConditionConfiguration;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * The window this closes is the one between a chunk being split out on the
 * manager and that chunk reaching the other machines. A job scheduled into
 * that window lands on a node with no file to translate and fails, and the
 * only reason it did not happen on the last run is that a node was held down
 * by hand.
 */
public class TestChunkStagedCondition {

  @Rule
  public TemporaryFolder folder = new TemporaryFolder();

  private File staging;
  private File nodesConf;

  @Before
  public void setUp() throws Exception {
    staging = folder.newFolder("staging");
    nodesConf = new File(folder.getRoot(), "nodes.conf");
  }

  @Test
  public void holdsWhenNothingHasBeenStagedYet() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    assertFalse("a chunk with no manifest anywhere must not be released",
        evaluate("chunk-0001.json"));
  }

  @Test
  public void releasesOnceEveryNodeHasTheChunk() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json", "chunk-0002.json");
    assertTrue(evaluate("chunk-0001.json"));
  }

  @Test
  public void holdsWhileOneOfTwoNodesIsStillMissingIt() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8", "gpu2 spaghetti2 8");
    writeManifest("gpu", "chunk-0001.json");
    writeManifest("gpu2", "chunk-0002.json");
    assertFalse("the slowest node decides when the chunk is releasable",
        evaluate("chunk-0001.json"));
  }

  @Test
  public void holdsAChunkThatWasNotPartOfTheStagedSet() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    assertFalse(evaluate("chunk-0009.json"));
  }

  /**
   * The manager is the first line and is never staged to, because it wrote
   * the chunks. Requiring a manifest for it would hold every task forever on
   * a cluster that is working perfectly.
   */
  @Test
  public void doesNotExpectAManifestForTheManager() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    assertTrue(evaluate("chunk-0001.json"));
    assertFalse("only the manager line should be skipped",
        new File(staging, "ninja.staged").exists());
  }

  /**
   * A plain single-machine install has no nodes.conf at all. Holding there
   * would deadlock every run on a cluster that has nowhere to stage to.
   */
  @Test
  public void releasesWhenThereIsNoClusterConfigured() throws Exception {
    assertTrue(evaluate("chunk-0001.json"));
  }

  @Test
  public void releasesWhenTheOnlyNodeIsTheManager() throws Exception {
    writeNodes("ninja localhost 8");
    assertTrue(evaluate("chunk-0001.json"));
  }

  @Test
  public void ignoresCommentsAndBlankLinesWhenFindingTheManager()
      throws Exception {
    writeNodes("# the first real line is this machine", "", "ninja localhost 8",
        "# and the rest are compute nodes", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    assertTrue("a comment above the manager line must not be taken for it",
        evaluate("chunk-0001.json"));
  }

  /**
   * Filename arrives as a full path on the manager while the manifest is
   * built from basenames on the node, where the absolute path is the same but
   * there is no reason to depend on that.
   */
  @Test
  public void comparesOnTheFileNameNotTheWholePath() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "/usr/local/bigtranslate/data/strings/chunk-0001.json");
    assertTrue(evaluate("/some/other/prefix/data/strings/chunk-0001.json"));
  }

  @Test
  public void holdsWhenThereIsNoFilenameToLookFor() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    assertFalse("without a chunk name the condition cannot be satisfied",
        evaluate(null));
  }

  @Test
  public void holdsWhenTheConditionIsNotConfigured() throws Exception {
    Metadata metadata = new Metadata();
    metadata.addMetadata("Filename", "chunk-0001.json");
    assertFalse(new ChunkStagedCondition().evaluate(metadata,
        new WorkflowConditionConfiguration()));
  }

  /**
   * Manifests are cached to keep a polling engine off the disk, so a node
   * staged after a first look must still be seen.
   */
  @Test
  public void picksUpAManifestWrittenAfterTheFirstEvaluation()
      throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    assertFalse(evaluate("chunk-0001.json"));
    writeManifest("gpu", "chunk-0001.json");
    assertTrue("staging after a hold must release the task",
        evaluate("chunk-0001.json"));
  }

  @Test
  public void picksUpAChunkAddedToAnExistingManifest() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    assertFalse(evaluate("chunk-0002.json"));
    writeManifest("gpu", "chunk-0001.json", "chunk-0002.json");
    assertTrue("a restaged manifest must not be served from the cache",
        evaluate("chunk-0002.json"));
  }

  @Test
  public void readsTheChunkFromAConfiguredMetadataKey() throws Exception {
    writeNodes("ninja localhost 8", "gpu spaghetti 8");
    writeManifest("gpu", "chunk-0001.json");
    Metadata metadata = new Metadata();
    metadata.addMetadata("ChunkFile", "chunk-0001.json");
    WorkflowConditionConfiguration config = config();
    config.addConfigProperty(ChunkStagedCondition.FILENAME_KEY, "ChunkFile");
    assertTrue(new ChunkStagedCondition().evaluate(metadata, config));
  }

  // ------------------------------------------------------------- helpers ---

  private boolean evaluate(String filename) {
    Metadata metadata = new Metadata();
    if (filename != null) {
      metadata.addMetadata("Filename", filename);
    }
    return new ChunkStagedCondition().evaluate(metadata, config());
  }

  private WorkflowConditionConfiguration config() {
    WorkflowConditionConfiguration config =
        new WorkflowConditionConfiguration();
    config.addConfigProperty(ChunkStagedCondition.STAGING_DIR,
        staging.getAbsolutePath());
    config.addConfigProperty(ChunkStagedCondition.NODES_FILE,
        nodesConf.getAbsolutePath());
    return config;
  }

  private void writeNodes(String... lines) throws Exception {
    write(nodesConf, lines);
  }

  private void writeManifest(String node, String... chunks) throws Exception {
    write(new File(staging, node + ChunkStagedCondition.MANIFEST_SUFFIX),
        chunks);
  }

  private void write(File file, String... lines) throws Exception {
    Writer writer = new OutputStreamWriter(new FileOutputStream(file),
        StandardCharsets.UTF_8);
    try {
      for (String line : lines) {
        writer.write(line);
        writer.write("\n");
      }
    } finally {
      writer.close();
    }
    // The cache keys on size and timestamp, and a test can rewrite a file
    // inside the filesystem's timestamp granularity. Staging in real life
    // takes minutes, so this is a property of the test rather than of the
    // condition, but a test that passes only on a coarse clock is no test.
    file.setLastModified(System.currentTimeMillis() + 1000L * lines.length);
  }
}
