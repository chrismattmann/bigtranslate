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

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * Telling a running translation from one that stopped.
 *
 * <p>The marker used to be evidence only that a run had once begun. A run
 * whose script died left one behind, and Gloss reported a translation in
 * progress for as long as the file existed: one sat for a day, naming the
 * previous afternoon's corpus, while a different run was genuinely under
 * way and invisible.</p>
 */
public class TestStaleRunMarker {

  private Map<String, Object> marker(Long heartbeatAt) {
    Map<String, Object> recorded = new LinkedHashMap<String, Object>();
    recorded.put("status", "TRANSLATING");
    recorded.put("path", "/corpus");
    recorded.put("startedAt", Long.valueOf(1L));
    if (heartbeatAt != null) {
      recorded.put("heartbeatAt", heartbeatAt);
    }
    return recorded;
  }

  @Test
  public void testAFreshHeartbeatIsARunningTranslation() {
    assertFalse(ProcessBtWrapper.isStale(
        marker(Long.valueOf(System.currentTimeMillis()))));
  }

  @Test
  public void testAHeartbeatThatStoppedIsNotARunningTranslation() {
    long longAgo = System.currentTimeMillis()
        - ProcessBtWrapper.STALE_AFTER_MILLIS - 1000L;
    assertTrue("a marker nobody is tending must not read as in progress",
        ProcessBtWrapper.isStale(marker(Long.valueOf(longAgo))));
  }

  @Test
  public void testAMarkerFromAnOlderVersionIsTrusted() {
    // No heartbeat at all: written before this existed. There is nothing
    // better to go on, so it is taken at face value as it always was.
    assertFalse(ProcessBtWrapper.isStale(marker(null)));
  }

  @Test
  public void testNoMarkerIsNotStale() {
    assertFalse(ProcessBtWrapper.isStale(null));
  }

  @Test
  public void testAnUnreadableHeartbeatIsTrusted() {
    Map<String, Object> recorded = marker(null);
    recorded.put("heartbeatAt", "not a number");
    assertFalse("a marker we cannot read is not evidence of a dead run",
        ProcessBtWrapper.isStale(recorded));
  }
}
