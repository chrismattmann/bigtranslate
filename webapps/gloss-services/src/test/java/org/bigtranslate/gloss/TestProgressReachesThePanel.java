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

import org.junit.Test;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * The chunk counts have to reach the panel however the run was started.
 *
 * <p>Gloss's progress pane shows a bar and a tally when it has
 * {@code chunksTotal}, and a tail of the log when it does not. The stages
 * write those counts into the run marker whether the run began on the
 * command line or from the Translate button.</p>
 *
 * <p>{@code snapshot()} only copied them through on the command line path.
 * A run started in Gloss leaves this object's own status at TRANSLATING,
 * which takes that branch out of play, so the one case where somebody is
 * certainly watching the panel is the one case the counts never reached
 * it.</p>
 */
public class TestProgressReachesThePanel {

  private static final String MARKER =
      "{\"status\": \"TRANSLATING\", \"startedBy\": \"cli\","
      + " \"path\": \"/corpus\", \"exclude\": \".*/\\\\.[^/]*(/.*)?\","
      + " \"startedAt\": 1788765472909, \"heartbeatAt\": %d,"
      + " \"stage\": \"translating\", \"chunksTotal\": 458,"
      + " \"chunksDone\": 401}";

  @Test
  public void theCountsReachACommandLineRun() throws Exception {
    Map<String, Object> snap = snapshotWithMarker();
    assertEquals(Long.valueOf(458L), snap.get("chunksTotal"));
    assertEquals(Long.valueOf(401L), snap.get("chunksDone"));
    assertEquals("translating", snap.get("stage"));
  }

  @Test
  public void aBackslashInTheExcludeDoesNotStopTheMarkerParsing()
      throws Exception {
    // The crawl's default exclude has one. Written unescaped the file was
    // not JSON, every reader lost the whole marker, and the panel lost the
    // path and the start time along with the counts.
    Map<String, Object> snap = snapshotWithMarker();
    assertEquals("/corpus", snap.get("path"));
    assertTrue("the marker did not parse", snap.get("startedAt") != null);
  }

  /** The branch a run started from the Translate button takes. */
  @Test
  public void theCountsAlsoReachARunStartedInGloss() throws Exception {
    File home = newHome();
    writeMarker(home);
    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      ProcessBtWrapper wrapper = ProcessBtWrapper.getInstance();
      // What translate() leaves behind while a run it started is under way.
      // Set directly because there is no seam for it and starting a real
      // run in a unit test is not the thing being checked.
      Field field = ProcessBtWrapper.class.getDeclaredField("status");
      field.setAccessible(true);
      Object before = field.get(wrapper);
      field.set(wrapper, ProcessBtWrapper.TRANSLATING);
      try {
        Map<String, Object> snap = wrapper.snapshot();
        assertEquals("a run started in Gloss shows no progress",
            Long.valueOf(458L), snap.get("chunksTotal"));
        assertEquals(Long.valueOf(401L), snap.get("chunksDone"));
      } finally {
        field.set(wrapper, before);
      }
    } finally {
      restore(previous);
    }
  }

  // ------------------------------------------------------------- helpers ---

  private Map<String, Object> snapshotWithMarker() throws Exception {
    File home = newHome();
    writeMarker(home);
    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      return ProcessBtWrapper.getInstance().snapshot();
    } finally {
      restore(previous);
    }
  }

  private File newHome() throws Exception {
    File home = File.createTempFile("gloss-home", "");
    assertTrue(home.delete() && home.mkdirs());
    return home;
  }

  private void writeMarker(File home) throws Exception {
    File data = new File(home, "data");
    assertTrue(data.mkdirs());
    Writer writer = new OutputStreamWriter(
        new FileOutputStream(new File(data, "run")), StandardCharsets.UTF_8);
    try {
      writer.write(String.format(MARKER, Long.valueOf(
          System.currentTimeMillis())));
    } finally {
      writer.close();
    }
  }

  private void restore(String previous) {
    if (previous == null) {
      System.clearProperty("BIGTRANSLATE_HOME");
    } else {
      System.setProperty("BIGTRANSLATE_HOME", previous);
    }
  }
}
