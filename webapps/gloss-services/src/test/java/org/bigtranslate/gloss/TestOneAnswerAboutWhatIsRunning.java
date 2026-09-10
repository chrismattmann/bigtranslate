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

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * One question about what is running should not have two answers.
 *
 * <p>/progress and /summary read the same object and disagreed: with a run
 * under way from the command line, /progress said TRANSLATING and /summary
 * said IDLE. /summary asked {@code getStatus()}, which is this process's
 * memory of a run it started itself and is empty for one it did not, while
 * /progress asked {@code snapshot()}, which reads the marker on disk.</p>
 *
 * <p>Nothing in the UI shows this field: the status badge reads /bt/status,
 * which already asked snapshot, and SummaryBar never looks at
 * summary.status. I claimed in #83 that the map page read it and so was the
 * page giving the wrong answer, and that was wrong -- the badge said IDLE
 * because the marker had been deleted, which is a different bug in the same
 * report. What is fixed here is an endpoint answering wrongly, not a page
 * displaying wrongly.</p>
 */
public class TestOneAnswerAboutWhatIsRunning {

  @Test
  public void testTheResolvedStatusIsTheOneSnapshotReports() throws Exception {
    final ProcessBtWrapper wrapper = ProcessBtWrapper.getInstance();
    withHome(new Runnable() {
      public void run() {
        assertEquals("the two must not be able to disagree",
            String.valueOf(wrapper.snapshot().get("status")),
            wrapper.resolvedStatus());
      }
    });
  }

  @Test
  public void testWithNothingRunningItIsIdle() throws Exception {
    final ProcessBtWrapper wrapper = ProcessBtWrapper.getInstance();
    withHome(new Runnable() {
      public void run() {
        assertEquals("no marker and nothing started here is IDLE, not null",
            ProcessBtWrapper.IDLE, wrapper.resolvedStatus());
      }
    });
  }

  /**
   * Without a home there is no marker to read, and the summary that used to
   * ask getStatus never needed one. It must not start failing the page.
   */
  @Test
  public void testItFallsBackRatherThanThrowing() {
    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.clearProperty("BIGTRANSLATE_HOME");
    try {
      assertEquals(ProcessBtWrapper.IDLE,
          ProcessBtWrapper.getInstance().resolvedStatus());
    } finally {
      if (previous != null) {
        System.setProperty("BIGTRANSLATE_HOME", previous);
      }
    }
  }

  private void withHome(Runnable body) throws Exception {
    File home = File.createTempFile("gloss-home", "");
    assertTrue(home.delete() && home.mkdirs());
    String previous = System.getProperty("BIGTRANSLATE_HOME");
    System.setProperty("BIGTRANSLATE_HOME", home.getAbsolutePath());
    try {
      body.run();
    } finally {
      if (previous == null) {
        System.clearProperty("BIGTRANSLATE_HOME");
      } else {
        System.setProperty("BIGTRANSLATE_HOME", previous);
      }
    }
  }
}
