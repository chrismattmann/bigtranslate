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

/**
 * Paths inside a BigTranslate deploy directory.
 *
 * Prefer {@code OODT_HOME} / {@code OODT_BASE} over {@code BIGTRANSLATE_HOME}:
 * {@code bin/oodt} derives those from its own location, while setenv.sh still
 * defaults {@code BIGTRANSLATE_HOME} to {@code /usr/local/bigtranslate} if it
 * has not been edited for this machine.
 */
public final class FileConstants {

  private FileConstants() {
  }

  public static String getHome() {
    String home = firstNonEmpty(
        System.getenv("OODT_HOME"),
        System.getenv("OODT_BASE"),
        System.getProperty("OODT_HOME"),
        System.getenv("BIGTRANSLATE_HOME"),
        System.getProperty("BIGTRANSLATE_HOME"));
    if (home == null || home.trim().isEmpty()) {
      throw new IllegalStateException(
          "OODT_HOME / BIGTRANSLATE_HOME is not set");
    }
    if (home.endsWith("/")) {
      home = home.substring(0, home.length() - 1);
    }
    return home;
  }

  public static String path(String additional) {
    return subdirectory(getHome(), additional);
  }

  /**
   * Resolve a path inside a deploy directory. Split out from {@link #path}
   * so tests can exercise the rule without this JVM's environment.
   */
  static String subdirectory(String home, String additional) {
    if (home.endsWith("/")) {
      home = home.substring(0, home.length() - 1);
    }
    if (additional == null || additional.isEmpty()) {
      return home;
    }
    if (additional.startsWith("/")) {
      return home + additional;
    }
    return home + "/" + additional;
  }

  public static String btCli() {
    return path("/bin/bigtranslate");
  }

  public static String logFile() {
    return path("/data/gloss_output.log");
  }

  public static String glossaryFile() {
    return path("/conf/glossary.es-en.tsv");
  }

  public static String cacheFile() {
    return path("/data/translationcache/cache.sqlite");
  }

  public static String archiveDir() {
    return path("/data/archive");
  }

  public static String jobsDir() {
    return path("/data/jobs");
  }

  public static String workflowDataDir() {
    return path("/data/workflow");
  }

  public static String filemgrUrl() {
    String url = firstNonEmpty(System.getenv("FILEMGR_URL"),
        System.getProperty("FILEMGR_URL"));
    return url == null ? "http://localhost:9000" : url;
  }

  public static String solrCoreUrl() {
    String url = firstNonEmpty(System.getenv("SOLR_URL"),
        System.getProperty("SOLR_URL"));
    return url == null ? "http://localhost:8983/solr/bigtranslate" : url;
  }

  public static String solrBaseUrl() {
    String core = solrCoreUrl();
    int slash = core.lastIndexOf('/');
    if (slash <= "http://localhost:8983/solr".length()) {
      return "http://localhost:8983/solr";
    }
    // core url is .../solr/bigtranslate -> .../solr
    int solr = core.lastIndexOf("/solr");
    if (solr >= 0) {
      return core.substring(0, solr + "/solr".length());
    }
    return core.substring(0, slash);
  }

  static String firstNonEmpty(String... values) {
    if (values == null) {
      return null;
    }
    for (int i = 0; i < values.length; i++) {
      if (values[i] != null && !values[i].trim().isEmpty()) {
        return values[i].trim();
      }
    }
    return null;
  }
}
