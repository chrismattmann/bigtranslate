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

import junit.framework.TestCase;

public class TestFileConstants extends TestCase {

  public void testResolvesUnderTheDeployDirectory() {
    assertEquals("/opt/bigtranslate/deploy/bin/bigtranslate",
        FileConstants.subdirectory("/opt/bigtranslate/deploy", "/bin/bigtranslate"));
  }

  public void testStripsATrailingSlashOnHome() {
    assertEquals("/srv/bt/data/jobs",
        FileConstants.subdirectory("/srv/bt/", "/data/jobs"));
  }

  public void testAcceptsARelativeSuffix() {
    assertEquals("/srv/bt/conf/glossary.es-en.tsv",
        FileConstants.subdirectory("/srv/bt", "conf/glossary.es-en.tsv"));
  }

  public void testDoesNotTruncateADirectoryThatHappensToContainTheName() {
    assertEquals("/home/bigtranslate-test/deploy/bin/bigtranslate",
        FileConstants.subdirectory("/home/bigtranslate-test/deploy",
            "/bin/bigtranslate"));
  }

  public void testAllPathsStayUnderHome() {
    String home = "/srv/bt/deploy";
    String[] subs = new String[] {
        "/bin/bigtranslate", "/data/gloss_output.log", "/conf/glossary.es-en.tsv",
        "/data/translationcache/cache.sqlite", "/data/archive", "/data/jobs"
    };
    for (int i = 0; i < subs.length; i++) {
      String resolved = FileConstants.subdirectory(home, subs[i]);
      assertTrue("[" + resolved + "] escaped home",
          resolved.startsWith(home + "/"));
    }
  }

  public void testFirstNonEmptySkipsBlanks() {
    assertEquals("keep", FileConstants.firstNonEmpty("", "  ", null, "keep"));
    assertNull(FileConstants.firstNonEmpty(null, "", "  "));
  }
}
