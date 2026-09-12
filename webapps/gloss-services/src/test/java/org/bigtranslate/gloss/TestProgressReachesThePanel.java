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


  // ------------------------------------------------ counted from disk ---
  //
  // Through the translate pass nothing writes the marker except the wait
  // loop in bin/bigtranslate, which carries no counts, so the panel has to
  // be able to work them out for itself. The rule is deliberately the same
  // one progress() uses in bin/bt-run-marker, and the two must agree.

  @Test
  public void nothingExtractedYetIsExtracting() throws Exception {
    File home = newHome();
    withHome(home, new Body() {
      public void run() {
        Map<String, Object> seen = ProcessBtWrapper.countChunks();
        assertEquals("extracting", seen.get("stage"));
        assertEquals(Long.valueOf(0L), seen.get("chunksTotal"));
      }
    });
  }

  @Test
  public void chunksMadeAndNoneTranslatedIsTranslating() throws Exception {
    File home = newHome();
    chunks(home, "strings", 458);
    withHome(home, new Body() {
      public void run() {
        Map<String, Object> seen = ProcessBtWrapper.countChunks();
        assertEquals("translating", seen.get("stage"));
        assertEquals(Long.valueOf(458L), seen.get("chunksTotal"));
        assertEquals(Long.valueOf(0L), seen.get("chunksDone"));
      }
    });
  }

  @Test
  public void theArchiveCounts() throws Exception {
    // On a distributed run the manager's own flat directory holds only the
    // share it translated itself; the archive is the only complete copy.
    // Counting the flat directory alone reported 43 of 458 while 121 were
    // done, and the stage never turned over to joining.
    File home = newHome();
    chunks(home, "strings", 458);
    chunks(home, "translated", 43);
    chunks(home, "translated-catalog", 121);
    withHome(home, new Body() {
      public void run() {
        assertEquals(Long.valueOf(121L),
            ProcessBtWrapper.countChunks().get("chunksDone"));
      }
    });
  }

  @Test
  public void aChunkInBothIsCountedOnce() throws Exception {
    File home = newHome();
    chunks(home, "strings", 10);
    chunks(home, "translated", 4);
    chunks(home, "translated-catalog", 4);
    withHome(home, new Body() {
      public void run() {
        assertEquals(Long.valueOf(4L),
            ProcessBtWrapper.countChunks().get("chunksDone"));
      }
    });
  }

  @Test
  public void everythingTranslatedIsJoining() throws Exception {
    File home = newHome();
    chunks(home, "strings", 12);
    chunks(home, "translated-catalog", 12);
    withHome(home, new Body() {
      public void run() {
        assertEquals("joining", ProcessBtWrapper.countChunks().get("stage"));
      }
    });
  }

  @Test
  public void theRateHasSomethingToMeasureOver() throws Exception {
    // chunksPerMinute() returns 0 without translatingSince, and the panel
    // then drops Rate and Remaining without saying why. The bar came up with
    // no chunks/min beside it for exactly this reason.
    File home = newHome();
    chunks(home, "strings", 458);
    chunks(home, "translated-catalog", 16);
    withHome(home, new Body() {
      public void run() {
        Object since = ProcessBtWrapper.countChunks().get("translatingSince");
        assertTrue("no translatingSince, so no rate", since instanceof Long);
        long when = ((Long) since).longValue();
        assertTrue("not a plausible epoch millis: " + when,
            when > 1000000000000L && when <= System.currentTimeMillis() + 1000L);
      }
    });
  }

  @Test
  public void nothingTranslatedYetHasNoRate() throws Exception {
    // Measuring from the start of the run would fold in the extract pass,
    // which on the full corpus is ten minutes of translating nothing.
    File home = newHome();
    chunks(home, "strings", 458);
    withHome(home, new Body() {
      public void run() {
        assertEquals(null,
            ProcessBtWrapper.countChunks().get("translatingSince"));
      }
    });
  }

  @Test
  public void itIsTheFirstChunkNotTheLast() throws Exception {
    File home = newHome();
    chunks(home, "strings", 10);
    chunks(home, "translated", 3);
    File dir = new File(new File(home, "data"), "translated");
    File first = new File(dir, "chunk-00000.json");
    final long old = System.currentTimeMillis() - (90L * 60L * 1000L);
    assertTrue(first.setLastModified(old));
    withHome(home, new Body() {
      public void run() {
        Object since = ProcessBtWrapper.countChunks().get("translatingSince");
        assertTrue(since instanceof Long);
        assertEquals("it took the newest, so the rate reads far too fast",
            old / 1000L, ((Long) since).longValue() / 1000L);
      }
    });
  }

  private interface Body {
    void run();
  }

  private void withHome(File home, Body body) {
    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      body.run();
    } finally {
      restore(previous);
    }
  }

  private void chunks(File home, String dir, int count) throws Exception {
    File where = new File(new File(home, "data"), dir);
    assertTrue(where.isDirectory() || where.mkdirs());
    for (int n = 0; n < count; n++) {
      assertTrue(new File(where, String.format("chunk-%05d.json",
          Integer.valueOf(n))).createNewFile());
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
