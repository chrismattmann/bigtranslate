/**
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
package org.bigtranslate.gloss;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

import org.apache.oodt.cas.filemgr.structs.Product;
import org.apache.oodt.cas.filemgr.structs.ProductPage;
import org.apache.oodt.cas.filemgr.structs.ProductType;
import org.apache.oodt.pcs.util.FileManagerUtils;

/**
 * One in-flight pipeline run. Gloss and the CLI share {@code bin/bigtranslate}:
 * Translate from the browser is that command, Reset from the browser is a
 * live wipe (Solr + File Manager + working dirs) because the CLI reset
 * requires the services to be down, which would take Gloss with them.
 */
public class ProcessBtWrapper {

  public static final String IDLE = "IDLE";
  public static final String TRANSLATING = "TRANSLATING";

  /**
   * How long a marker may go unrefreshed before it counts as dead. The
   * writer beats it every poll, so this is many polls: a slow machine
   * should not be mistaken for a stopped run.
   */
  static final long STALE_AFTER_MILLIS = 10L * 60L * 1000L;

  /** How far before a run's start its own log may already have been written. */
  static final long STALE_LOG_MARGIN_MILLIS = 60L * 1000L;

  /** What the stages record about how far along they are. */
  private static final String[] PROGRESS_KEYS = {
      "stage", "chunksTotal", "chunksDone", "translatingSince"};
  public static final String RESETTING = "RESETTING";
  public static final String ERROR = "ERROR";

  static final String[] WIPE_TYPES = {
      "EmploymentJobAggregatesTsv",
      "EmploymentJobAggregatesTsvSplit"
  };

  private static final Logger LOG = Logger.getLogger(ProcessBtWrapper.class.getName());
  private static final ProcessBtWrapper INSTANCE = new ProcessBtWrapper();
  private static final int MAX_RESET_TRIES = 10;

  private String status = IDLE;
  private String path = "";
  private String exclude = "";
  private String message = "";
  private long startedAt;
  private Thread worker;

  public static ProcessBtWrapper getInstance() {
    return INSTANCE;
  }

  ProcessBtWrapper() {
  }

  /**
   * What is happening, from where it is written down before this process's
   * own memory.
   *
   * <p>
   * A translation is normally started from the command line, and this web
   * application had no way of knowing that: the fields below are set only
   * when a run is started through Gloss, so Gloss reported IDLE throughout
   * somebody else's run. The marker is written by whichever side starts one.
   * </p>
   */
  public synchronized Map<String, Object> snapshot() {
    Map<String, Object> snap = new LinkedHashMap<String, Object>();

    Map<String, Object> recorded = RunMarker.read();
    if (isStale(recorded)) {
      // A marker whose heartbeat stopped is a run that stopped. Left alone
      // it is reported as in progress for as long as the file exists: one
      // sat for a day naming the previous afternoon's corpus while a
      // different run was genuinely under way.
      LOG.log(Level.INFO, "Clearing a run marker whose heartbeat stopped");
      RunMarker.clear();
      recorded = null;
    }
    if (recorded != null && !TRANSLATING.equals(status)
        && !RESETTING.equals(status)) {
      // Something is running and it was not started here.
      snap.put("status", asText(recorded.get("status"), TRANSLATING));
      snap.put("path", asText(recorded.get("path"), ""));
      snap.put("exclude", asText(recorded.get("exclude"), ""));
      snap.put("message", "started from the command line");
      snap.put("startedAt", recorded.get("startedAt"));
      // What it has actually done. A status of TRANSLATING and a log tail
      // says almost nothing at hour eleven of a run; how many chunks of
      // how many, and at what rate, says all of it.
      for (String key : PROGRESS_KEYS) {
        if (recorded.get(key) != null) {
          snap.put(key, recorded.get(key));
        }
      }
      return snap;
    }

    snap.put("status", status);
    snap.put("path", path);
    snap.put("exclude", exclude);
    snap.put("message", message);
    snap.put("startedAt", startedAt == 0 ? null : Long.valueOf(startedAt));
    return snap;
  }

  /**
   * Whether a recorded run has stopped being refreshed.
   *
   * <p>The writer beats the marker on every poll of its wait loop, so a
   * heartbeat older than many polls means nothing is tending it. A marker
   * with no heartbeat at all was written by an older version and is
   * trusted, there being nothing better to go on.</p>
   */
  static boolean isStale(Map<String, Object> recorded) {
    if (recorded == null) {
      return false;
    }
    Object beat = recorded.get("heartbeatAt");
    if (beat == null) {
      return false;
    }
    try {
      long last = Long.parseLong(String.valueOf(beat).trim());
      return System.currentTimeMillis() - last > STALE_AFTER_MILLIS;
    } catch (NumberFormatException e) {
      return false;
    }
  }

  private static String asText(Object value, String fallback) {
    if (value == null) {
      return fallback;
    }
    String text = String.valueOf(value);
    return text.isEmpty() ? fallback : text;
  }

  public synchronized String getStatus() {
    return status;
  }

  public synchronized String getPath() {
    return path;
  }

  public synchronized void translate(String productPath, String excludePattern)
      throws IOException {
    if (TRANSLATING.equals(status) || RESETTING.equals(status)) {
      throw new IOException("A run is already " + status);
    }
    if (productPath == null || productPath.trim().isEmpty()) {
      throw new IOException("path is required");
    }
    File dir = new File(productPath);
    if (!dir.exists()) {
      throw new IOException("Path does not exist: " + productPath);
    }
    this.path = productPath.trim();
    this.exclude = excludePattern == null ? "" : excludePattern.trim();
    this.status = TRANSLATING;
    // Written down as well as held, so a reader that is not this process --
    // another browser, a restarted Tomcat -- can still see the run.
    RunMarker.write(TRANSLATING, "gloss", productPath, excludePattern);
    this.message = "";
    this.startedAt = System.currentTimeMillis();
    final List<String> command = buildTranslateCommand(
        FileConstants.btCli(), this.path, this.exclude);
    worker = new Thread(new Runnable() {
      @Override
      public void run() {
        int code = -1;
        try {
          appendLog("START translate " + command);
          code = runCommand(command);
          synchronized (ProcessBtWrapper.this) {
            if (code == 0) {
              status = IDLE;
              RunMarker.clear();
              message = "translate finished";
            } else {
              status = ERROR;
              RunMarker.clear();
              message = "translate exited " + code;
            }
          }
          appendLog("END translate exit=" + code);
        } catch (Exception e) {
          synchronized (ProcessBtWrapper.this) {
            status = ERROR;
            RunMarker.clear();
            message = e.getLocalizedMessage();
          }
          appendLog("ERROR translate " + e.getLocalizedMessage());
        }
      }
    }, "gloss-translate");
    worker.setDaemon(true);
    worker.start();
  }

  public synchronized void reset() throws IOException {
    if (TRANSLATING.equals(status) || RESETTING.equals(status)) {
      throw new IOException("A run is already " + status);
    }
    status = RESETTING;
    RunMarker.write(RESETTING, "gloss", "", "");
    message = "";
    startedAt = System.currentTimeMillis();
    try {
      appendLog("START reset");
      liveReset();
      status = IDLE;
      RunMarker.clear();
      message = "reset finished";
      path = "";
      exclude = "";
      appendLog("END reset");
    } catch (IOException e) {
      status = ERROR;
      RunMarker.clear();
      message = e.getLocalizedMessage();
      appendLog("ERROR reset " + e.getLocalizedMessage());
      throw e;
    }
  }

  void liveReset() throws IOException {
    wipeSolr();
    wipeFileManager();
    wipeDirectoryContents(FileConstants.archiveDir());
    wipeDirectoryContents(FileConstants.jobsDir());
    deleteQuietly(FileConstants.workflowDataDir());
  }

  static List<String> buildTranslateCommand(String cli, String productPath,
      String excludePattern) {
    List<String> command = new ArrayList<String>();
    command.add(cli);
    command.add("translate");
    if (excludePattern != null && !excludePattern.isEmpty()) {
      command.add("--exclude");
      command.add(excludePattern);
    }
    command.add(productPath);
    return command;
  }

  int runCommand(List<String> command) throws IOException, InterruptedException {
    ProcessBuilder builder = new ProcessBuilder(command);
    builder.redirectErrorStream(true);
    Process process = builder.start();
    pipeToLog(process.getInputStream());
    return process.waitFor();
  }

  void wipeSolr() {
    try {
      new SolrSupport().deleteAll();
      appendLog("wiped Solr core bigtranslate");
    } catch (Exception e) {
      LOG.warning("Unable to wipe Solr: " + e.getLocalizedMessage());
      appendLog("WARN Solr wipe failed: " + e.getLocalizedMessage());
    }
  }

  void wipeFileManager() {
    FileManagerUtils fm;
    try {
      fm = new FileManagerUtils(FileConstants.filemgrUrl());
    } catch (Exception e) {
      LOG.warning("Unable to reach File Manager: " + e.getLocalizedMessage());
      appendLog("WARN File Manager unreachable: " + e.getLocalizedMessage());
      return;
    }
    for (int t = 0; t < WIPE_TYPES.length; t++) {
      String typeName = WIPE_TYPES[t];
      int tries = 0;
      ProductType type = fm.safeGetProductTypeByName(typeName);
      while (type != null && fm.safeGetNumProducts(type) > 0
          && tries <= MAX_RESET_TRIES) {
        wipeProductType(fm, typeName);
        tries++;
        type = fm.safeGetProductTypeByName(typeName);
      }
    }
  }

  private void wipeProductType(FileManagerUtils fm, String productTypeName) {
    ProductType type = fm.safeGetProductTypeByName(productTypeName);
    if (type == null) {
      return;
    }
    ProductPage page = fm.safeFirstPage(type);
    while (page != null) {
      List<Product> products = page.getPageProducts();
      if (products != null) {
        for (int i = 0; i < products.size(); i++) {
          Product product = products.get(i);
          try {
            fm.getFmgrClient().removeProduct(product);
          } catch (Exception e) {
            LOG.warning("Unable to remove product " + product.getProductId()
                + ": " + e.getLocalizedMessage());
          }
        }
      }
      if (page.isLastPage()) {
        break;
      }
      try {
        page = fm.getFmgrClient().getNextPage(type, page);
      } catch (Exception e) {
        break;
      }
    }
  }

  static void wipeDirectoryContents(String dirPath) {
    Path dir = Paths.get(dirPath);
    if (!Files.isDirectory(dir)) {
      return;
    }
    DirectoryStream<Path> stream = null;
    try {
      stream = Files.newDirectoryStream(dir);
      for (Path child : stream) {
        deleteRecursively(child);
      }
    } catch (IOException e) {
      LOG.warning("Unable to wipe " + dirPath + ": " + e.getLocalizedMessage());
    } finally {
      if (stream != null) {
        try {
          stream.close();
        } catch (IOException ignore) {
        }
      }
    }
  }

  static void deleteQuietly(String path) {
    deleteRecursively(Paths.get(path));
  }

  static void deleteRecursively(Path path) {
    if (path == null || !Files.exists(path)) {
      return;
    }
    try {
      Files.walk(path).sorted(Comparator.reverseOrder()).forEach(p -> {
        try {
          Files.deleteIfExists(p);
        } catch (IOException e) {
          LOG.warning("Unable to delete " + p + ": " + e.getLocalizedMessage());
        }
      });
    } catch (IOException e) {
      LOG.warning("Unable to walk " + path + ": " + e.getLocalizedMessage());
    }
  }

  /**
   * The tail of whichever log this run is writing.
   *
   * <p>
   * Gloss keeps a log of what it did itself, and reads it here. A run started
   * from the command line writes to the deployment's own log instead, so this
   * returned nothing for the whole of every real run and the page sat on
   * "Waiting for log..." -- waiting for a file that was never going to be
   * written. Prefer the one with something in it, most recent first.
   * </p>
   */
  public static String readLogTail(int maxBytes) {
    File log = mostRecentLog();
    if (log == null || !log.exists()) {
      return "";
    }
    try {
      byte[] all = Files.readAllBytes(log.toPath());
      if (all.length <= maxBytes) {
        return new String(all, StandardCharsets.UTF_8);
      }
      return new String(all, all.length - maxBytes, maxBytes, StandardCharsets.UTF_8);
    } catch (IOException e) {
      return e.getLocalizedMessage();
    }
  }

  /** Whichever of the two logs was written to last, or null if neither was. */
  static File mostRecentLog() {
    return mostRecentLog(runStartedAt());
  }

  /**
   * The most recent log, so long as it belongs to the run in progress.
   *
   * <p>Picking the newest of the two files says nothing about which run
   * wrote it. A run that writes no log of its own leaves the previous
   * run's as the newest, and the page then shows that instead: one
   * displayed eleven thousand seconds of a translation from two days
   * earlier, next to a progress bar describing the run actually
   * happening.</p>
   *
   * <p>A log last written before this run began is a log from an earlier
   * one. Showing nothing is the honest answer, and the panel already says
   * so in words.</p>
   */
  static File mostRecentLog(long runStartedAt) {
    File[] candidates = {
        new File(FileConstants.logFile()),
        new File(FileConstants.path("/logs/bigtranslate.log"))
    };
    File best = null;
    for (File candidate : candidates) {
      if (!candidate.exists() || candidate.length() == 0) {
        continue;
      }
      // A margin, because a run's first log line lands a moment after the
      // marker that announces it.
      if (runStartedAt > 0
          && candidate.lastModified() < runStartedAt - STALE_LOG_MARGIN_MILLIS) {
        continue;
      }
      if (best == null || candidate.lastModified() > best.lastModified()) {
        best = candidate;
      }
    }
    return best;
  }

  /** When the run in progress began, or 0 if none is recorded. */
  private static long runStartedAt() {
    Map<String, Object> recorded = RunMarker.read();
    if (recorded == null) {
      return 0L;
    }
    Object started = recorded.get("startedAt");
    if (started == null) {
      return 0L;
    }
    try {
      return Long.parseLong(String.valueOf(started).trim());
    } catch (NumberFormatException e) {
      return 0L;
    }
  }

  public static long countJobDirs() {
    Path jobs = Paths.get(FileConstants.jobsDir());
    if (!Files.isDirectory(jobs)) {
      return 0L;
    }
    long count = 0L;
    try {
      DirectoryStream<Path> stream = Files.newDirectoryStream(jobs);
      try {
        for (Path child : stream) {
          if (Files.isDirectory(child)) {
            count++;
          }
        }
      } finally {
        stream.close();
      }
    } catch (IOException e) {
      return count;
    }
    return count;
  }

  synchronized void appendLog(String line) {
    File log = new File(FileConstants.logFile());
    try {
      File parent = log.getParentFile();
      if (parent != null && !parent.exists()) {
        parent.mkdirs();
      }
      OutputStreamWriter writer = new OutputStreamWriter(
          new FileOutputStream(log, true), StandardCharsets.UTF_8);
      try {
        writer.write(new Date().toString());
        writer.write("  ");
        writer.write(line);
        writer.write(System.lineSeparator());
      } finally {
        writer.close();
      }
    } catch (IOException e) {
      LOG.warning("Unable to write Gloss log: " + e.getLocalizedMessage());
    }
  }

  private void pipeToLog(InputStream processInput) throws IOException {
    BufferedReader reader = new BufferedReader(
        new InputStreamReader(processInput, StandardCharsets.UTF_8));
    try {
      String line;
      while ((line = reader.readLine()) != null) {
        appendLog(line);
      }
    } finally {
      reader.close();
    }
  }

  // visible for tests
  static List<String> wipeTypes() {
    return Arrays.asList(WIPE_TYPES);
  }
}
