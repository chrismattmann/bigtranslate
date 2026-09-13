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

import org.bigtranslate.gloss.rest.ServicesRestResource;
import org.junit.Test;

import java.io.File;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

/**
 * An idle deployment is not in the middle of a stage.
 *
 * <p>The chunk counts are read from directories, which is what makes them
 * right through the translate pass when nothing is writing the marker. It is
 * also what makes them wrong afterwards: a finished run leaves those
 * directories full, so with nothing running at all /progress answered</p>
 *
 * <pre>
 *   "status": "IDLE", "stage": "joining",
 *   "chunksTotal": 458, "chunksDone": 458
 * </pre>
 *
 * <p>which is last week's run described as though it were this one. Nothing
 * renders it today -- Gloss draws the pane only while it is busy -- but an
 * endpoint that answers a question it was not asked is how the next reader
 * gets misled, and this project has been caught by exactly that more than
 * once.</p>
 */
public class TestAnIdleDeploymentHasNoStage {

  @Test
  public void anIdleDeploymentReportsNoStage() throws Exception {
    File home = File.createTempFile("gloss-home", "");
    assertTrue(home.delete() && home.mkdirs());
    // A finished run's leavings: chunks made and every one translated.
    File data = new File(home, "data");
    chunks(new File(data, "strings"), 458);
    chunks(new File(data, "translated-catalog"), 458);

    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      // Nothing running and no marker, so snapshot() says IDLE.
      Map<String, Object> progress = new ServicesRestResource().progress();
      assertEquals(ProcessBtWrapper.IDLE, progress.get("status"));
      assertNull("an idle deployment reported a stage in progress",
          progress.get("stage"));
      assertNull(progress.get("chunksTotal"));
      assertNull(progress.get("chunksDone"));
    } finally {
      if (previous == null) {
        System.clearProperty("BIGTRANSLATE_HOME");
      } else {
        System.setProperty("BIGTRANSLATE_HOME", previous);
      }
    }
  }

  /** The counting itself is unchanged; only what /progress does with it. */
  @Test
  public void theCountsAreStillThereToBeAskedFor() throws Exception {
    File home = File.createTempFile("gloss-home", "");
    assertTrue(home.delete() && home.mkdirs());
    chunks(new File(new File(home, "data"), "strings"), 458);

    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      assertEquals(Long.valueOf(458L),
          ProcessBtWrapper.countChunks().get("chunksTotal"));
    } finally {
      if (previous == null) {
        System.clearProperty("BIGTRANSLATE_HOME");
      } else {
        System.setProperty("BIGTRANSLATE_HOME", previous);
      }
    }
  }

  private void chunks(File where, int count) throws Exception {
    assertTrue(where.mkdirs());
    for (int n = 0; n < count; n++) {
      assertTrue(new File(where,
          String.format("chunk-%05d.json", Integer.valueOf(n)))
          .createNewFile());
    }
  }
}
