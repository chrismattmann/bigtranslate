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

  public synchronized Map<String, Object> snapshot() {
    Map<String, Object> snap = new LinkedHashMap<String, Object>();
    snap.put("status", status);
    snap.put("path", path);
    snap.put("exclude", exclude);
    snap.put("message", message);
    snap.put("startedAt", startedAt == 0 ? null : Long.valueOf(startedAt));
    return snap;
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
              message = "translate finished";
            } else {
              status = ERROR;
              message = "translate exited " + code;
            }
          }
          appendLog("END translate exit=" + code);
        } catch (Exception e) {
          synchronized (ProcessBtWrapper.this) {
            status = ERROR;
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
    message = "";
    startedAt = System.currentTimeMillis();
    try {
      appendLog("START reset");
      liveReset();
      status = IDLE;
      message = "reset finished";
      path = "";
      exclude = "";
      appendLog("END reset");
    } catch (IOException e) {
      status = ERROR;
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

  public static String readLogTail(int maxBytes) {
    File log = new File(FileConstants.logFile());
    if (!log.exists()) {
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
