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
package org.bigtranslate.gloss;

import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * What is running, written down where anything can read it.
 *
 * <p>
 * Gloss used to keep this in a field of the web application, set when a run
 * was started through Gloss and by nothing else. A translation started from
 * the command line -- which is how runs are started -- therefore left Gloss
 * reporting IDLE for its entire duration, with no repository, no start time
 * and no way to tell a busy deployment from an idle one. The fact lived in
 * the heap of whichever process you were not looking at.
 * </p>
 *
 * <p>
 * A file in the deployment outlives both, so the side that did not start the
 * run can still describe it, and a Tomcat restarted mid-run does not lose it.
 * </p>
 */
public final class RunMarker {

  private static final Logger LOG = Logger.getLogger(RunMarker.class.getName());

  private RunMarker() {
  }

  static String markerPath() {
    return FileConstants.path("/data/run");
  }

  /** Record that something is running. */
  public static synchronized void write(String status, String startedBy,
      String path, String exclude) {
    File marker = new File(markerPath());
    File parent = marker.getParentFile();
    if (parent != null && !parent.exists() && !parent.mkdirs()) {
      LOG.log(Level.WARNING, "Unable to create " + parent
          + "; the running translation will not be recorded");
      return;
    }

    StringBuilder json = new StringBuilder();
    json.append('{');
    field(json, "status", status, true);
    field(json, "startedBy", startedBy, false);
    field(json, "path", path, false);
    field(json, "exclude", exclude, false);
    json.append(",\"startedAt\":").append(System.currentTimeMillis());
    json.append('}');

    FileWriter writer = null;
    try {
      writer = new FileWriter(marker);
      writer.write(json.toString());
    } catch (Exception e) {
      LOG.log(Level.WARNING, "Unable to record the running translation: "
          + e.getMessage());
    } finally {
      if (writer != null) {
        try {
          writer.close();
        } catch (Exception ignored) {
          // Nothing useful to do about a failed close of a marker file.
        }
      }
    }
  }

  /** Record that nothing is running. */
  public static synchronized void clear() {
    File marker = new File(markerPath());
    if (marker.exists() && !marker.delete()) {
      LOG.log(Level.WARNING, "Unable to remove " + marker
          + "; Gloss will go on reporting a run that has ended");
    }
  }

  /** Whether a run is recorded. Existence is the durable fact. */
  public static synchronized boolean isRecorded() {
    return new File(markerPath()).exists();
  }

  /**
   * The recorded run, or null when there is none.
   *
   * <p>
   * Parsed by hand rather than with a JSON library: this module has none on
   * its compile path, and the file is written by {@link #write} and by
   * bin/bigtranslate, both of which produce flat string fields.
   * </p>
   */
  public static synchronized Map<String, Object> read() {
    File marker = new File(markerPath());
    if (!marker.exists()) {
      return null;
    }
    String body;
    try {
      body = new String(Files.readAllBytes(Paths.get(marker.getPath())),
          StandardCharsets.UTF_8);
    } catch (Exception e) {
      // Unreadable is not the same as absent: a marker caught mid-write says
      // nothing about whether a run is happening, and reporting IDLE on that
      // basis is the bug this class exists to prevent.
      LOG.log(Level.WARNING, "Unable to read the run marker: " + e.getMessage());
      return null;
    }

    Map<String, Object> run = new LinkedHashMap<String, Object>();
    for (String name : new String[] {"status", "startedBy", "path", "exclude"}) {
      String value = stringField(body, name);
      if (value != null) {
        run.put(name, value);
      }
    }
    Long startedAt = longField(body, "startedAt");
    if (startedAt != null) {
      run.put("startedAt", startedAt);
    }
    return run.isEmpty() ? null : run;
  }

  private static void field(StringBuilder json, String name, String value,
      boolean first) {
    if (!first) {
      json.append(',');
    }
    json.append('"').append(name).append("\":\"")
        .append(escape(value == null ? "" : value)).append('"');
  }

  private static String escape(String value) {
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
        .replace("\n", " ").replace("\r", " ");
  }

  private static String stringField(String body, String name) {
    String key = "\"" + name + "\"";
    int at = body.indexOf(key);
    if (at < 0) {
      return null;
    }
    int colon = body.indexOf(':', at + key.length());
    if (colon < 0) {
      return null;
    }
    int open = body.indexOf('"', colon);
    if (open < 0) {
      return null;
    }
    StringBuilder value = new StringBuilder();
    for (int i = open + 1; i < body.length(); i++) {
      char c = body.charAt(i);
      if (c == '\\' && i + 1 < body.length()) {
        value.append(body.charAt(++i));
      } else if (c == '"') {
        return value.toString();
      } else {
        value.append(c);
      }
    }
    return null;
  }

  private static Long longField(String body, String name) {
    String key = "\"" + name + "\"";
    int at = body.indexOf(key);
    if (at < 0) {
      return null;
    }
    int colon = body.indexOf(':', at + key.length());
    if (colon < 0) {
      return null;
    }
    StringBuilder digits = new StringBuilder();
    for (int i = colon + 1; i < body.length(); i++) {
      char c = body.charAt(i);
      if (Character.isDigit(c)) {
        digits.append(c);
      } else if (digits.length() > 0) {
        break;
      }
    }
    try {
      return digits.length() == 0 ? null : Long.valueOf(digits.toString());
    } catch (NumberFormatException e) {
      return null;
    }
  }
}
