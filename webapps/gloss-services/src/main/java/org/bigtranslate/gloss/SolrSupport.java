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

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.Socket;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Same-origin Solr access for Gloss. Solr runs on its own port (8983), so
 * the browser talks to gloss-services and this class forwards select and
 * the handful of admin calls the UI needs. Update is only used by reset.
 */
public class SolrSupport {

  private static final Logger LOG = Logger.getLogger(SolrSupport.class.getName());
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final int CONNECT_MS = 2000;
  private static final int READ_MS = 30000;

  private final String coreUrl;

  public SolrSupport() {
    this(FileConstants.solrCoreUrl());
  }

  public SolrSupport(String coreUrl) {
    this.coreUrl = coreUrl.endsWith("/")
        ? coreUrl.substring(0, coreUrl.length() - 1) : coreUrl;
  }

  public boolean ping() {
    try {
      String body = get(coreUrl + "/admin/ping?wt=json");
      return body != null && body.contains("\"status\":\"OK\"");
    } catch (Exception e) {
      return false;
    }
  }

  public long numFound() throws IOException {
    String body = get(coreUrl + "/select?q=*:*&rows=0&wt=json");
    JsonNode node = MAPPER.readTree(body);
    JsonNode found = node.path("response").path("numFound");
    return found.isNumber() ? found.asLong() : 0L;
  }

  static final String[] FACET_FIELDS = {
      "location", "department", "jobtype", "company", "salary",
      "start", "duration", "applications"
  };

  static final String[] TABLE_FIELDS = {
      "id", "title", "company", "location", "department", "jobtype",
      "salary", "start", "duration", "postedDate", "url"
  };

  /**
   * Page of postings. {@code q} is a Solr query (default {@code *:*});
   * {@code fqs} are already-quoted filter queries such as {@code location:"Costa Rica"}.
   */
  public Map<String, Object> table(String q, int start, int rows, List<String> fqs)
      throws IOException {
    return table(q, start, rows, fqs, "postedDate", "desc");
  }

  public Map<String, Object> table(String q, int start, int rows, List<String> fqs,
      String sortField, String sortDir) throws IOException {
    if (start < 0) {
      start = 0;
    }
    if (rows <= 0 || rows > 100) {
      rows = 25;
    }
    String sort = sortClause(sortField, sortDir);
    StringBuilder url = new StringBuilder(coreUrl);
    url.append("/select?wt=json&q=").append(encode(blankToStar(q)));
    url.append("&start=").append(start);
    url.append("&rows=").append(rows);
    url.append("&sort=").append(encode(sort));
    url.append("&fl=").append(encode(join(TABLE_FIELDS)));
    appendFqs(url, fqs);
    JsonNode root = MAPPER.readTree(get(url.toString()));
    JsonNode response = root.path("response");
    List<Map<String, Object>> docs = new ArrayList<Map<String, Object>>();
    JsonNode arr = response.path("docs");
    if (arr.isArray()) {
      for (int i = 0; i < arr.size(); i++) {
        docs.add(docToRow(arr.get(i)));
      }
    }
    Map<String, Object> result = new LinkedHashMap<String, Object>();
    result.put("numFound", Long.valueOf(response.path("numFound").asLong(0L)));
    result.put("start", Integer.valueOf(start));
    result.put("rows", Integer.valueOf(rows));
    result.put("sort", sort);
    result.put("docs", docs);
    return result;
  }

  /**
   * One posting, every stored field. The table links here instead of the
   * original job-board URL.
   */
  public Map<String, Object> record(String id) throws IOException {
    if (id == null || id.trim().isEmpty()) {
      throw new IOException("id is required");
    }
    String escaped = id.trim().replace("\\", "\\\\").replace("\"", "\\\"");
    String body = get(coreUrl + "/select?wt=json&rows=1&q="
        + encode("id:\"" + escaped + "\""));
    JsonNode docs = MAPPER.readTree(body).path("response").path("docs");
    Map<String, Object> result = new LinkedHashMap<String, Object>();
    if (!docs.isArray() || docs.size() == 0) {
      result.put("found", Boolean.FALSE);
      result.put("id", id.trim());
      result.put("fields", new ArrayList<Object>());
      return result;
    }
    result.put("found", Boolean.TRUE);
    result.put("id", id.trim());
    result.put("fields", docToFields(docs.get(0)));
    return result;
  }

  /**
   * Facet counts for the employment fields, honoring the same {@code q} and
   * filters as the table so a click on one list narrows the others.
   */
  public Map<String, Object> facets(String q, List<String> fqs) throws IOException {
    StringBuilder url = new StringBuilder(coreUrl);
    url.append("/select?wt=json&q=").append(encode(blankToStar(q)));
    url.append("&rows=0&facet=true&facet.mincount=1&facet.limit=40&facet.missing=false");
    for (int i = 0; i < FACET_FIELDS.length; i++) {
      url.append("&facet.field=").append(encode(FACET_FIELDS[i]));
    }
    appendFqs(url, fqs);
    JsonNode root = MAPPER.readTree(get(url.toString()));
    JsonNode fields = root.path("facet_counts").path("facet_fields");
    List<Map<String, Object>> groups = new ArrayList<Map<String, Object>>();
    for (int i = 0; i < FACET_FIELDS.length; i++) {
      String name = FACET_FIELDS[i];
      Map<String, Object> group = new LinkedHashMap<String, Object>();
      group.put("field", name);
      group.put("values", parseFacet(fields.path(name)));
      groups.add(group);
    }
    Map<String, Object> result = new LinkedHashMap<String, Object>();
    result.put("numFound", Long.valueOf(root.path("response").path("numFound").asLong(0L)));
    result.put("facets", groups);
    return result;
  }

  static final String[] SORT_FIELDS = {
      "title", "company", "location", "jobtype", "salary", "postedDate"
  };

  static final String[] RECORD_SKIP = {
      "_version_", "text", "text_rev", "content"
  };

  static final String[] RECORD_ORDER = {
      "title", "company", "location", "department", "jobtype", "salary",
      "start", "duration", "applications", "contactPerson", "phoneNumber",
      "faxNumber", "postedDate", "firstSeenDate", "lastSeenDate",
      "latitude", "longitude", "url", "id"
  };

  public static String sortClause(String field, String dir) {
    if (!isSortField(field)) {
      field = "postedDate";
    }
    boolean asc = dir != null && "asc".equalsIgnoreCase(dir.trim());
    return field + (asc ? " asc" : " desc");
  }

  static boolean isSortField(String field) {
    if (field == null) {
      return false;
    }
    for (int i = 0; i < SORT_FIELDS.length; i++) {
      if (SORT_FIELDS[i].equals(field)) {
        return true;
      }
    }
    return false;
  }

  static String blankToStar(String q) {
    if (q == null || q.trim().isEmpty()) {
      return "*:*";
    }
    return q.trim();
  }

  public static String fq(String field, String value) {
    if (!isFacetField(field) || value == null || value.trim().isEmpty()) {
      return null;
    }
    String escaped = value.trim().replace("\\", "\\\\").replace("\"", "\\\"");
    return field + ":\"" + escaped + "\"";
  }

  static boolean isFacetField(String field) {
    if (field == null) {
      return false;
    }
    for (int i = 0; i < FACET_FIELDS.length; i++) {
      if (FACET_FIELDS[i].equals(field)) {
        return true;
      }
    }
    return false;
  }

  static List<Map<String, Object>> parseFacet(JsonNode node) {
    List<Map<String, Object>> values = new ArrayList<Map<String, Object>>();
    if (node == null || !node.isArray()) {
      return values;
    }
    for (int i = 0; i + 1 < node.size(); i += 2) {
      JsonNode nameNode = node.get(i);
      if (nameNode == null || nameNode.isNull()) {
        continue;
      }
      String name = nameNode.asText("");
      if (name.trim().isEmpty()) {
        continue;
      }
      Map<String, Object> pair = new LinkedHashMap<String, Object>();
      pair.put("value", name);
      pair.put("count", Long.valueOf(node.get(i + 1).asLong(0L)));
      values.add(pair);
    }
    return values;
  }

  private static void appendFqs(StringBuilder url, List<String> fqs) {
    if (fqs == null) {
      return;
    }
    for (int i = 0; i < fqs.size(); i++) {
      String fq = fqs.get(i);
      if (fq != null && !fq.trim().isEmpty()) {
        url.append("&fq=").append(encode(fq));
      }
    }
  }

  private static String join(String[] parts) {
    StringBuilder b = new StringBuilder();
    for (int i = 0; i < parts.length; i++) {
      if (i > 0) {
        b.append(',');
      }
      b.append(parts[i]);
    }
    return b.toString();
  }

  static Map<String, Object> docToRow(JsonNode doc) {
    Map<String, Object> row = new LinkedHashMap<String, Object>();
    for (int i = 0; i < TABLE_FIELDS.length; i++) {
      String field = TABLE_FIELDS[i];
      String value = text(doc, field);
      row.put(field, value == null ? "" : value);
    }
    return row;
  }

  static List<Map<String, String>> docToFields(JsonNode doc) {
    List<Map<String, String>> fields = new ArrayList<Map<String, String>>();
    java.util.Set<String> seen = new java.util.HashSet<String>();
    for (int i = 0; i < RECORD_ORDER.length; i++) {
      String name = RECORD_ORDER[i];
      if (doc.has(name)) {
        fields.add(fieldEntry(name, fieldValue(doc.get(name))));
        seen.add(name);
      }
    }
    java.util.Iterator<String> names = doc.fieldNames();
    while (names.hasNext()) {
      String name = names.next();
      if (seen.contains(name) || skipRecordField(name)) {
        continue;
      }
      fields.add(fieldEntry(name, fieldValue(doc.get(name))));
    }
    return fields;
  }

  static boolean skipRecordField(String name) {
    if (name != null && name.startsWith("_")) {
      return true;
    }
    for (int i = 0; i < RECORD_SKIP.length; i++) {
      if (RECORD_SKIP[i].equals(name)) {
        return true;
      }
    }
    return false;
  }

  static Map<String, String> fieldEntry(String name, String value) {
    Map<String, String> entry = new LinkedHashMap<String, String>();
    entry.put("name", name);
    entry.put("value", value == null ? "" : value);
    return entry;
  }

  static String fieldValue(JsonNode node) {
    if (node == null || node.isNull()) {
      return "";
    }
    if (node.isArray()) {
      StringBuilder b = new StringBuilder();
      for (int i = 0; i < node.size(); i++) {
        if (i > 0) {
          b.append(", ");
        }
        b.append(node.get(i).asText(""));
      }
      return b.toString();
    }
    return node.asText("");
  }

  /**
   * Facet {@code location} and attach coordinates: real lat/lng from a
   * sample of docs when present, otherwise {@link LocationGeocoder}.
   */
  public Map<String, Object> map(LocationGeocoder geocoder) throws IOException {
    String body = get(coreUrl
        + "/select?q=*:*&rows=0&wt=json&facet=true&facet.field=location"
        + "&facet.mincount=1&facet.limit=500&facet.missing=true");
    JsonNode root = MAPPER.readTree(body);
    long total = root.path("response").path("numFound").asLong(0L);
    JsonNode fields = root.path("facet_counts").path("facet_fields").path("location");

    Map<String, SampleCoord> samples = sampleCoords();

    List<Map<String, Object>> bubbles = new ArrayList<Map<String, Object>>();
    long unlocated = 0L;
    if (fields.isArray()) {
      for (int i = 0; i + 1 < fields.size(); i += 2) {
        JsonNode nameNode = fields.get(i);
        long count = fields.get(i + 1).asLong(0L);
        if (nameNode.isNull()) {
          unlocated += count;
          continue;
        }
        String location = nameNode.asText("");
        if (location.trim().isEmpty()) {
          unlocated += count;
          continue;
        }
        Double lat = null;
        Double lng = null;
        String source = "geocoder";
        SampleCoord sample = samples.get(location);
        if (sample != null) {
          lat = Double.valueOf(sample.lat);
          lng = Double.valueOf(sample.lng);
          source = "solr";
        } else {
          LocationGeocoder.Coord coord = geocoder.geocode(location);
          if (coord != null) {
            lat = Double.valueOf(coord.lat);
            lng = Double.valueOf(coord.lng);
          }
        }
        if (lat == null) {
          unlocated += count;
          continue;
        }
        Map<String, Object> bubble = new LinkedHashMap<String, Object>();
        bubble.put("location", location);
        bubble.put("lat", lat);
        bubble.put("lng", lng);
        bubble.put("count", Long.valueOf(count));
        bubble.put("source", source);
        bubbles.add(bubble);
      }
    }

    Map<String, Object> result = new LinkedHashMap<String, Object>();
    result.put("solrDocs", Long.valueOf(total));
    result.put("bubbles", bubbles);
    result.put("unlocated", Long.valueOf(unlocated));
    return result;
  }

  public void deleteAll() throws IOException {
    postJson(coreUrl + "/update?commit=true", "{\"delete\":{\"query\":\"*:*\"}}");
  }

  public String select(Map<String, List<String>> params) throws IOException {
    StringBuilder url = new StringBuilder(coreUrl);
    url.append("/select");
    String sep = "?";
    for (Map.Entry<String, List<String>> entry : params.entrySet()) {
      List<String> values = entry.getValue();
      if (values == null) {
        continue;
      }
      for (int i = 0; i < values.size(); i++) {
        url.append(sep);
        url.append(encode(entry.getKey())).append('=').append(encode(values.get(i)));
        sep = "&";
      }
    }
    return get(url.toString());
  }

  public static boolean portOpen(String host, int port) {
    Socket socket = null;
    try {
      socket = new Socket();
      socket.connect(new InetSocketAddress(host, port), 750);
      return true;
    } catch (IOException e) {
      return false;
    } finally {
      if (socket != null) {
        try {
          socket.close();
        } catch (IOException ignore) {
        }
      }
    }
  }

  private Map<String, SampleCoord> sampleCoords() {
    Map<String, SampleCoord> samples = new LinkedHashMap<String, SampleCoord>();
    try {
      String body = get(coreUrl
          + "/select?q=*:*&fq=latitude:[*+TO+*]&fq=-latitude:\"\"&fl=location,latitude,longitude"
          + "&rows=1000&wt=json");
      JsonNode docs = MAPPER.readTree(body).path("response").path("docs");
      if (!docs.isArray()) {
        return samples;
      }
      for (int i = 0; i < docs.size(); i++) {
        JsonNode doc = docs.get(i);
        String location = text(doc, "location");
        Double lat = LocationGeocoder.parseDouble(text(doc, "latitude"));
        Double lng = LocationGeocoder.parseDouble(text(doc, "longitude"));
        if (location == null || lat == null || lng == null) {
          continue;
        }
        if (!samples.containsKey(location)) {
          samples.put(location, new SampleCoord(lat.doubleValue(), lng.doubleValue()));
        }
      }
    } catch (Exception e) {
      LOG.fine("Could not sample lat/lng from Solr: " + e.getLocalizedMessage());
    }
    return samples;
  }

  private static String text(JsonNode doc, String field) {
    JsonNode node = doc.get(field);
    if (node == null || node.isNull()) {
      return null;
    }
    if (node.isArray() && node.size() > 0) {
      return node.get(0).asText(null);
    }
    return node.asText(null);
  }

  private static String encode(String value) {
    try {
      return URLEncoder.encode(value, "UTF-8");
    } catch (Exception e) {
      return value;
    }
  }

  String get(String target) throws IOException {
    return exchange("GET", target, null);
  }

  String postJson(String target, String json) throws IOException {
    return exchange("POST", target, json);
  }

  private String exchange(String method, String target, String json) throws IOException {
    HttpURLConnection connection = null;
    try {
      connection = (HttpURLConnection) new URL(target).openConnection();
      connection.setRequestMethod(method);
      connection.setConnectTimeout(CONNECT_MS);
      connection.setReadTimeout(READ_MS);
      if (json != null) {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Content-Length", String.valueOf(bytes.length));
        OutputStream out = connection.getOutputStream();
        try {
          out.write(bytes);
        } finally {
          out.close();
        }
      }
      int code = connection.getResponseCode();
      InputStream stream = code < 400
          ? connection.getInputStream() : connection.getErrorStream();
      String body = read(stream);
      if (code >= 400) {
        throw new IOException("Solr HTTP " + code + " from " + target + ": " + body);
      }
      return body;
    } finally {
      if (connection != null) {
        connection.disconnect();
      }
    }
  }

  private static String read(InputStream stream) throws IOException {
    if (stream == null) {
      return "";
    }
    try {
      ByteArrayOutputStream buffer = new ByteArrayOutputStream();
      byte[] bytes = new byte[4096];
      int count;
      while ((count = stream.read(bytes)) != -1) {
        buffer.write(bytes, 0, count);
      }
      return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
    } finally {
      stream.close();
    }
  }

  private static final class SampleCoord {
    final double lat;
    final double lng;

    SampleCoord(double lat, double lng) {
      this.lat = lat;
      this.lng = lng;
    }
  }
}
