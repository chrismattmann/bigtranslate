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

import java.io.File;
import java.nio.file.Files;
import java.util.List;

import junit.framework.TestCase;

public class TestProcessBtWrapper extends TestCase {

  public void testTranslateCommandIsTheCli() {
    List<String> command = ProcessBtWrapper.buildTranslateCommand(
        "/opt/bt/bin/bigtranslate", "/data/untranslated", "");
    assertEquals(3, command.size());
    assertEquals("/opt/bt/bin/bigtranslate", command.get(0));
    assertEquals("translate", command.get(1));
    assertEquals("/data/untranslated", command.get(2));
  }

  public void testTranslateCommandPassesExcludeThrough() {
    List<String> command = ProcessBtWrapper.buildTranslateCommand(
        "/opt/bt/bin/bigtranslate", "/data/untranslated", ".git");
    assertEquals(5, command.size());
    assertEquals("--exclude", command.get(2));
    assertEquals(".git", command.get(3));
    assertEquals("/data/untranslated", command.get(4));
  }

  public void testWipeTypesAreTheEmploymentProducts() {
    List<String> types = ProcessBtWrapper.wipeTypes();
    assertTrue(types.contains("EmploymentJobAggregatesTsv"));
    assertTrue(types.contains("EmploymentJobTranslated"));
    assertEquals(5, types.size());
  }

  public void testWipeDirectoryContentsLeavesTheDirectory() throws Exception {
    File tmp = Files.createTempDirectory("gloss-wipe").toFile();
    File child = new File(tmp, "job-1");
    assertTrue(child.mkdir());
    Files.write(new File(child, "out.json").toPath(), "x".getBytes("UTF-8"));
    ProcessBtWrapper.wipeDirectoryContents(tmp.getAbsolutePath());
    assertTrue(tmp.isDirectory());
    assertEquals(0, tmp.list().length);
    tmp.delete();
  }

  public void testSnapshotStartsIdle() {
    ProcessBtWrapper wrapper = new ProcessBtWrapper();
    assertEquals(ProcessBtWrapper.IDLE, wrapper.getStatus());
    assertEquals("", wrapper.getPath());
  }
}
