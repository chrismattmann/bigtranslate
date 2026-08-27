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
package org.bigtranslate.gloss.rest;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

import javax.ws.rs.DefaultValue;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.QueryParam;
import javax.ws.rs.core.MediaType;

import org.bigtranslate.gloss.FileConstants;
import org.bigtranslate.gloss.LocationGeocoder;
import org.bigtranslate.gloss.ProcessBtWrapper;
import org.bigtranslate.gloss.SolrSupport;

@Path("/service")
@Produces(MediaType.APPLICATION_JSON)
public class ServicesRestResource {

  private static final Logger LOG = Logger.getLogger(ServicesRestResource.class.getName());
  private final LocationGeocoder geocoder = new LocationGeocoder();

  @GET
  @Path("/status/oodt")
  public Map<String, Object> oodtStatus() {
    Map<String, Object> status = new LinkedHashMap<String, Object>();
    boolean fm = SolrSupport.portOpen("localhost", 9000);
    boolean wm = SolrSupport.portOpen("localhost", 9001);
    boolean rm = SolrSupport.portOpen("localhost", 9002);
    boolean tomcat = SolrSupport.portOpen("localhost", 8080);
    boolean solr = SolrSupport.portOpen("localhost", 8983);
    status.put("fm", Boolean.valueOf(fm));
    status.put("wm", Boolean.valueOf(wm));
    status.put("rm", Boolean.valueOf(rm));
    status.put("tomcat", Boolean.valueOf(tomcat));
    status.put("solr", Boolean.valueOf(solr));
    status.put("up", Boolean.valueOf(fm && wm && rm && tomcat));
    return status;
  }

  @GET
  @Path("/progress")
  public Map<String, Object> progress() {
    Map<String, Object> progress = new LinkedHashMap<String, Object>();
    progress.putAll(ProcessBtWrapper.getInstance().snapshot());
    progress.put("jobDirs", Long.valueOf(ProcessBtWrapper.countJobDirs()));
    try {
      progress.put("solrDocs", Long.valueOf(new SolrSupport().numFound()));
    } catch (Exception e) {
      progress.put("solrDocs", Long.valueOf(0));
      progress.put("solrError", e.getLocalizedMessage());
    }
    return progress;
  }

  @GET
  @Path("/summary")
  public Map<String, Object> summary() {
    Map<String, Object> summary = new LinkedHashMap<String, Object>();
    long solrDocs = 0L;
    long locations = 0L;
    try {
      Map<String, Object> map = new SolrSupport().map(geocoder);
      Object docs = map.get("solrDocs");
      if (docs instanceof Number) {
        solrDocs = ((Number) docs).longValue();
      }
      Object bubbles = map.get("bubbles");
      if (bubbles instanceof List) {
        locations = ((List<?>) bubbles).size();
      }
    } catch (Exception e) {
      summary.put("solrError", e.getLocalizedMessage());
    }
    summary.put("solrDocs", Long.valueOf(solrDocs));
    summary.put("locations", Long.valueOf(locations));
    try {
      summary.putAll(cacheStats());
      summary.put("glossaryEntries", Integer.valueOf(readGlossary().size()));
    } catch (Exception e) {
      summary.put("entries", Long.valueOf(0));
      summary.put("glossaryEntries", Integer.valueOf(0));
    }
    summary.put("status", ProcessBtWrapper.getInstance().getStatus());
    return summary;
  }

  @GET
  @Path("/map")
  public Map<String, Object> map() {
    try {
      return new SolrSupport().map(geocoder);
    } catch (Exception e) {
      LOG.warning("map failed: " + e.getLocalizedMessage());
      Map<String, Object> empty = new LinkedHashMap<String, Object>();
      empty.put("solrDocs", Long.valueOf(0));
      empty.put("bubbles", new ArrayList<Object>());
      empty.put("unlocated", Long.valueOf(0));
      empty.put("error", e.getLocalizedMessage());
      return empty;
    }
  }

  @GET
  @Path("/table")
  public Map<String, Object> table(
      @QueryParam("q") String q,
      @QueryParam("start") @DefaultValue("0") int start,
      @QueryParam("rows") @DefaultValue("25") int rows,
      @QueryParam("field") List<String> fields,
      @QueryParam("value") List<String> values,
      @QueryParam("sort") String sort,
      @QueryParam("dir") String dir) {
    try {
      return new SolrSupport().table(q, start, rows, toFqs(fields, values), sort, dir);
    } catch (Exception e) {
      LOG.warning("table failed: " + e.getLocalizedMessage());
      Map<String, Object> empty = new LinkedHashMap<String, Object>();
      empty.put("numFound", Long.valueOf(0));
      empty.put("start", Integer.valueOf(start));
      empty.put("rows", Integer.valueOf(rows));
      empty.put("docs", new ArrayList<Object>());
      empty.put("error", e.getLocalizedMessage());
      return empty;
    }
  }

  @GET
  @Path("/facets")
  public Map<String, Object> facets(
      @QueryParam("q") String q,
      @QueryParam("field") List<String> fields,
      @QueryParam("value") List<String> values) {
    try {
      return new SolrSupport().facets(q, toFqs(fields, values));
    } catch (Exception e) {
      LOG.warning("facets failed: " + e.getLocalizedMessage());
      Map<String, Object> empty = new LinkedHashMap<String, Object>();
      empty.put("numFound", Long.valueOf(0));
      empty.put("facets", new ArrayList<Object>());
      empty.put("error", e.getLocalizedMessage());
      return empty;
    }
  }

  @GET
  @Path("/record")
  public Map<String, Object> record(@QueryParam("id") String id) {
    try {
      return new SolrSupport().record(id);
    } catch (Exception e) {
      LOG.warning("record failed: " + e.getLocalizedMessage());
      Map<String, Object> empty = new LinkedHashMap<String, Object>();
      empty.put("found", Boolean.FALSE);
      empty.put("id", id == null ? "" : id);
      empty.put("fields", new ArrayList<Object>());
      empty.put("error", e.getLocalizedMessage());
      return empty;
    }
  }

  public static List<String> toFqs(List<String> fields, List<String> values) {
    List<String> fqs = new ArrayList<String>();
    if (fields == null || values == null) {
      return fqs;
    }
    int n = Math.min(fields.size(), values.size());
    for (int i = 0; i < n; i++) {
      String fq = SolrSupport.fq(fields.get(i), values.get(i));
      if (fq != null) {
        fqs.add(fq);
      }
    }
    return fqs;
  }

  @GET
  @Path("/glossary")
  public Map<String, Object> glossary() {
    Map<String, Object> body = new LinkedHashMap<String, Object>();
    List<Map<String, String>> entries = readGlossary();
    body.put("path", FileConstants.glossaryFile());
    body.put("entries", entries);
    return body;
  }

  @GET
  @Path("/cache")
  public Map<String, Object> cache() {
    return cacheStats();
  }

  static List<Map<String, String>> readGlossary() {
    List<Map<String, String>> entries = new ArrayList<Map<String, String>>();
    File file = new File(FileConstants.glossaryFile());
    if (!file.isFile()) {
      return entries;
    }
    try {
      BufferedReader reader = new BufferedReader(new InputStreamReader(
          new FileInputStream(file), StandardCharsets.UTF_8));
      try {
        String line;
        while ((line = reader.readLine()) != null) {
          String trimmed = line.trim();
          if (trimmed.isEmpty() || trimmed.charAt(0) == '#') {
            continue;
          }
          int tab = trimmed.indexOf('\t');
          if (tab <= 0) {
            continue;
          }
          Map<String, String> entry = new LinkedHashMap<String, String>();
          entry.put("source", trimmed.substring(0, tab));
          entry.put("target", trimmed.substring(tab + 1));
          entries.add(entry);
        }
      } finally {
        reader.close();
      }
    } catch (Exception e) {
      LOG.warning("Unable to read glossary: " + e.getLocalizedMessage());
    }
    return entries;
  }

  static Map<String, Object> cacheStats() {
    Map<String, Object> stats = new LinkedHashMap<String, Object>();
    File file = new File(FileConstants.cacheFile());
    stats.put("path", file.getAbsolutePath());
    stats.put("exists", Boolean.valueOf(file.isFile()));
    stats.put("sizeBytes", Long.valueOf(file.isFile() ? file.length() : 0L));
    long entries = 0L;
    if (file.isFile()) {
      Connection conn = null;
      try {
        Class.forName("org.sqlite.JDBC");
        conn = DriverManager.getConnection("jdbc:sqlite:" + file.getAbsolutePath());
        Statement st = conn.createStatement();
        ResultSet rs = st.executeQuery("SELECT COUNT(*) FROM translation");
        if (rs.next()) {
          entries = rs.getLong(1);
        }
        rs.close();
        st.close();
      } catch (Exception e) {
        stats.put("error", e.getLocalizedMessage());
      } finally {
        if (conn != null) {
          try {
            conn.close();
          } catch (Exception ignore) {
          }
        }
      }
    }
    stats.put("entries", Long.valueOf(entries));
    return stats;
  }
}
