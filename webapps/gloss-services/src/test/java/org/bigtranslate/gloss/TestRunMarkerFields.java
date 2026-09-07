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

import org.junit.After;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

/**
 * Reading a marker off disk, rather than building one in memory.
 *
 * <p>The staleness tests next door construct the map by hand, so they say
 * nothing about which fields the parser actually produces. That gap hid two
 * bugs at once. {@code read} pulled out only status, startedBy, path, exclude
 * and startedAt, so the progress panel drew no meter -- the counts it renders
 * were never in the map -- and {@code isStale} never fired once, because it
 * reads heartbeatAt and heartbeatAt was never parsed. The guard against
 * reporting a dead run as live could not have worked in any deployment.</p>
 *
 * <p>So these go through the file.</p>
 */
public class TestRunMarkerFields {

  @Rule
  public TemporaryFolder folder = new TemporaryFolder();

  private String previousHome;

  @Before
  public void pointHomeAtATempDirectory() throws Exception {
    previousHome = System.getProperty("OODT_HOME");
    System.setProperty("OODT_HOME", folder.getRoot().getAbsolutePath());
    assertTrue(new File(folder.getRoot(), "data").mkdirs());
  }

  @After
  public void restoreHome() {
    if (previousHome == null) {
      System.clearProperty("OODT_HOME");
    } else {
      System.setProperty("OODT_HOME", previousHome);
    }
  }

  private void writeMarker(String json) throws Exception {
    FileOutputStream out = new FileOutputStream(RunMarker.markerPath());
    try {
      out.write(json.getBytes(StandardCharsets.UTF_8));
    } finally {
      out.close();
    }
  }

  /** A marker as bin/bt-run-marker writes it mid-translation. */
  private static final String MID_RUN =
      "{\"status\": \"TRANSLATING\", \"startedBy\": \"workflow\","
      + " \"path\": \"/corpus\", \"exclude\": \"\","
      + " \"startedAt\": 1788764908909, \"heartbeatAt\": 1788816028909,"
      + " \"stage\": \"translating\", \"chunksTotal\": 458,"
      + " \"chunksDone\": 401, \"translatingSince\": 1788765472909}";

  @Test
  public void testTheProgressFieldsSurviveTheParser() throws Exception {
    writeMarker(MID_RUN);
    Map<String, Object> run = RunMarker.read();
    assertNotNull(run);
    assertEquals("translating", run.get("stage"));
    assertEquals(Long.valueOf(458L), run.get("chunksTotal"));
    assertEquals(Long.valueOf(401L), run.get("chunksDone"));
    assertEquals(Long.valueOf(1788765472909L), run.get("translatingSince"));
  }

  @Test
  public void testTheHeartbeatSurvivesTheParser() throws Exception {
    // Without this, isStale reads a null and every dead run reports as live.
    writeMarker(MID_RUN);
    assertEquals(Long.valueOf(1788816028909L),
        RunMarker.read().get("heartbeatAt"));
  }

  @Test
  public void testAMarkerWhoseHeartbeatStoppedReadsAsStale() throws Exception {
    long longAgo = System.currentTimeMillis()
        - ProcessBtWrapper.STALE_AFTER_MILLIS - 60000L;
    writeMarker("{\"status\": \"TRANSLATING\", \"path\": \"/corpus\","
        + " \"startedAt\": 1, \"heartbeatAt\": " + longAgo + "}");
    assertTrue("a marker read off disk must reach isStale with its heartbeat",
        ProcessBtWrapper.isStale(RunMarker.read()));
  }

  @Test
  public void testTheOriginalFieldsStillSurvive() throws Exception {
    writeMarker(MID_RUN);
    Map<String, Object> run = RunMarker.read();
    assertEquals("TRANSLATING", run.get("status"));
    assertEquals("workflow", run.get("startedBy"));
    assertEquals("/corpus", run.get("path"));
    assertEquals(Long.valueOf(1788764908909L), run.get("startedAt"));
  }

  @Test
  public void testAMarkerWithoutProgressFieldsStillReads() throws Exception {
    // Written by an older bin/bigtranslate. Absent is absent, not zero: a
    // meter drawn from a missing count would read 0 of 0.
    writeMarker("{\"status\": \"TRANSLATING\", \"path\": \"/corpus\","
        + " \"startedAt\": 1788764908909}");
    Map<String, Object> run = RunMarker.read();
    assertEquals("TRANSLATING", run.get("status"));
    assertEquals(null, run.get("chunksTotal"));
    assertEquals(null, run.get("stage"));
  }
}
