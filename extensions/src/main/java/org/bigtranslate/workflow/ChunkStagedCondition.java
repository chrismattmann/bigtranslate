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
import org.apache.oodt.cas.workflow.structs.WorkflowConditionInstance;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Holds a chunk translation until that chunk exists on every compute node.
 *
 * <p>A translate task reads its chunk from a node-local path. The chunks are
 * produced on the manager and copied outwards by {@code bt-cluster stage}, so
 * between the split finishing and the staging finishing there is a window in
 * which the Resource Manager will happily schedule a chunk onto a node that
 * does not have it yet. Every job placed in that window fails.
 *
 * <p>What we did instead, for one run, was keep the second node's batch stub
 * down until staging was over. That works, but it is a hack with two bad
 * properties: it takes a healthy node out of the cluster in order to express
 * a timing constraint, and it lives in the head of whoever is running the
 * cluster rather than in the policy. This condition is the same constraint,
 * written down.
 *
 * <p>The condition is evaluated by the Workflow Manager, not by the node that
 * will eventually run the task, so it cannot stat the node's disk and ask
 * directly. It reads instead the manifests {@code bt-cluster stage} leaves
 * behind on the manager: one file per node, listing the chunk file names
 * confirmed present on that node once its copy finished. Because any queued
 * task may be scheduled to any node, a chunk is releasable only when every
 * node has it, so this holds all translate tasks until the slowest node is
 * staged, which is precisely what taking the stub down achieved.
 *
 * <p>Absent evidence means "not yet", never "go ahead": a missing or
 * unreadable manifest holds the task, on the same reasoning as
 * {@code ProductCountMatchesCondition}, where a count that could not be read
 * is not a count of zero. The single deliberate exception is a missing
 * {@code nodes.conf}, which is what a plain single-machine install looks
 * like. There are no remote nodes to stage to there and nothing to wait for,
 * and holding would deadlock every single-node run forever.
 */
public class ChunkStagedCondition implements WorkflowConditionInstance {

  private static final Logger LOG =
      Logger.getLogger(ChunkStagedCondition.class.getName());

  static final String STAGING_DIR = "StagingDir";
  static final String NODES_FILE = "NodesFile";
  static final String FILENAME_KEY = "FilenameKey";

  static final String DEFAULT_FILENAME_KEY = "Filename";
  static final String MANIFEST_SUFFIX = ".staged";

  /**
   * A node id that no manifest can match, used to hold every task when
   * nodes.conf exists but cannot be read.
   */
  private static final String UNREADABLE = " unreadable-nodes-conf";

  /**
   * Manifests are read on every evaluation of every queued task, which for a
   * few hundred chunks against a polling engine is a great deal of
   * re-reading of a file that changes once per run. Keyed on size and
   * timestamp so a restaged manifest is still picked up; bt-cluster renames
   * the finished file into place, so a manifest never grows in place under a
   * reader and any change of contents is a change of one or both of these.
   */
  private static final Map<String, CachedManifest> CACHE =
      new ConcurrentHashMap<String, CachedManifest>();

  public ChunkStagedCondition() {
    super();
  }

  public boolean evaluate(Metadata metadata,
      WorkflowConditionConfiguration config) {
    String stagingDir = config.getProperty(STAGING_DIR);
    String nodesFile = config.getProperty(NODES_FILE);
    if (stagingDir == null || nodesFile == null) {
      LOG.log(Level.SEVERE, "Cannot evaluate without [" + STAGING_DIR
          + "] and [" + NODES_FILE + "]");
      return false;
    }

    String filenameKey = config.getProperty(FILENAME_KEY);
    if (filenameKey == null || filenameKey.trim().length() == 0) {
      filenameKey = DEFAULT_FILENAME_KEY;
    }

    String chunk = baseName(
        metadata != null ? metadata.getMetadata(filenameKey) : null);
    if (chunk == null) {
      LOG.log(Level.SEVERE, "Cannot evaluate without a [" + filenameKey
          + "] to look for; holding");
      return false;
    }

    List<String> nodes = computeNodes(new File(nodesFile));
    if (nodes == null) {
      // No nodes.conf: a single-machine install, where the chunk was written
      // by the split on this very disk. Nothing is staged anywhere, so there
      // is nothing to wait for.
      LOG.log(Level.FINE, "No [" + nodesFile + "]; treating as a single-node "
          + "install and releasing [" + chunk + "]");
      return true;
    }
    if (nodes.isEmpty()) {
      LOG.log(Level.FINE, "No compute nodes beyond the manager in ["
          + nodesFile + "]; releasing [" + chunk + "]");
      return true;
    }

    for (String node : nodes) {
      File manifest = new File(stagingDir, node + MANIFEST_SUFFIX);
      Set<String> staged = read(manifest);
      if (staged == null) {
        LOG.log(Level.FINE, "No staging manifest for [" + node + "] at ["
            + manifest + "]; holding [" + chunk + "]");
        return false;
      }
      if (!staged.contains(chunk)) {
        LOG.log(Level.FINE, "[" + chunk + "] is not staged on [" + node
            + "]; holding");
        return false;
      }
    }

    LOG.log(Level.FINE, "[" + chunk + "] is staged on all of " + nodes);
    return true;
  }

  /**
   * The compute nodes: every node in {@code nodes.conf} but the first, which
   * is the manager and already holds the chunks because it wrote them.
   *
   * @return null when the file does not exist, which is a single-machine
   *         install rather than an error
   */
  static List<String> computeNodes(File nodesConf) {
    if (!nodesConf.isFile()) {
      return null;
    }
    List<String> ids = new ArrayList<String>();
    BufferedReader reader = null;
    try {
      reader = new BufferedReader(new InputStreamReader(
          new FileInputStream(nodesConf), StandardCharsets.UTF_8));
      String line;
      boolean seenManager = false;
      while ((line = reader.readLine()) != null) {
        String trimmed = line.trim();
        if (trimmed.length() == 0 || trimmed.startsWith("#")) {
          continue;
        }
        if (!seenManager) {
          seenManager = true;
          continue;
        }
        ids.add(trimmed.split("\\s+")[0]);
      }
      return ids;
    } catch (Exception e) {
      // Distinct from having no file at all: the cluster is configured and we
      // could not read how, so hold rather than assume a single node.
      LOG.log(Level.WARNING, "Could not read [" + nodesConf + "]: "
          + e.getMessage());
      return Collections.singletonList(UNREADABLE);
    } finally {
      close(reader);
    }
  }

  /**
   * The chunk names staged on one node, or null if that cannot be determined,
   * which the caller treats as "not yet".
   */
  static Set<String> read(File manifest) {
    if (!manifest.isFile()) {
      return null;
    }
    long modified = manifest.lastModified();
    long length = manifest.length();
    String key = manifest.getAbsolutePath();
    CachedManifest cached = CACHE.get(key);
    if (cached != null && cached.modified == modified
        && cached.length == length) {
      return cached.names;
    }

    Set<String> names = new HashSet<String>();
    BufferedReader reader = null;
    try {
      reader = new BufferedReader(new InputStreamReader(
          new FileInputStream(manifest), StandardCharsets.UTF_8));
      String line;
      while ((line = reader.readLine()) != null) {
        String trimmed = line.trim();
        if (trimmed.length() > 0) {
          names.add(baseName(trimmed));
        }
      }
    } catch (Exception e) {
      LOG.log(Level.WARNING, "Could not read staging manifest [" + manifest
          + "]: " + e.getMessage());
      return null;
    } finally {
      close(reader);
    }
    CACHE.put(key, new CachedManifest(modified, length, names));
    return names;
  }

  static String baseName(String path) {
    if (path == null) {
      return null;
    }
    String trimmed = path.trim();
    if (trimmed.length() == 0) {
      return null;
    }
    int slash = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
    return slash >= 0 ? trimmed.substring(slash + 1) : trimmed;
  }

  private static void close(BufferedReader reader) {
    if (reader != null) {
      try {
        reader.close();
      } catch (Exception ignored) {
        // Nothing useful to do about a failed close of a file we only read.
      }
    }
  }

  private static final class CachedManifest {
    private final long modified;
    private final long length;
    private final Set<String> names;

    private CachedManifest(long modified, long length, Set<String> names) {
      this.modified = modified;
      this.length = length;
      this.names = names;
    }
  }
}
