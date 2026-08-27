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

import java.util.Arrays;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import junit.framework.TestCase;

import org.bigtranslate.gloss.rest.ServicesRestResource;

public class TestSolrSupport extends TestCase {

  public void testBlankQueryBecomesMatchAll() {
    assertEquals("*:*", SolrSupport.blankToStar(null));
    assertEquals("*:*", SolrSupport.blankToStar("  "));
    assertEquals("Java", SolrSupport.blankToStar(" Java "));
  }

  public void testFqQuotesAndEscapes() {
    assertEquals("location:\"Costa Rica\"", SolrSupport.fq("location", "Costa Rica"));
    assertEquals("jobtype:\"Full Time\"", SolrSupport.fq("jobtype", "Full Time"));
    assertEquals("company:\"Acme \\\"Ltd\\\"\"", SolrSupport.fq("company", "Acme \"Ltd\""));
  }

  public void testFqRejectsUnknownFields() {
    assertNull(SolrSupport.fq("password", "secret"));
    assertNull(SolrSupport.fq("location", ""));
    assertNull(SolrSupport.fq(null, "Costa Rica"));
  }

  public void testParseFacetPairsSkipsMissingAndEmpty() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    List<Map<String, Object>> values = SolrSupport.parseFacet(
        mapper.readTree("[\"Costa Rica\",4210,\"\",3,null,1,\"Mexico\",3890]"));
    assertEquals(2, values.size());
    assertEquals("Costa Rica", values.get(0).get("value"));
    assertEquals(Long.valueOf(4210), values.get(0).get("count"));
    assertEquals("Mexico", values.get(1).get("value"));
  }

  public void testToFqsZipsParallelQueryParams() {
    List<String> fqs = ServicesRestResource.toFqs(
        Arrays.asList("location", "jobtype", "bogus"),
        Arrays.asList("Costa Rica", "Full Time", "x"));
    assertEquals(2, fqs.size());
    assertEquals("location:\"Costa Rica\"", fqs.get(0));
    assertEquals("jobtype:\"Full Time\"", fqs.get(1));
  }

  public void testSortClauseWhitelistsColumnsAndDefaultsToPostedDateDesc() {
    assertEquals("title asc", SolrSupport.sortClause("title", "asc"));
    assertEquals("company desc", SolrSupport.sortClause("company", "DESC"));
    assertEquals("postedDate asc", SolrSupport.sortClause("password", "asc"));
    assertEquals("postedDate desc", SolrSupport.sortClause(null, null));
    assertEquals("postedDate asc", SolrSupport.sortClause("postedDate", "asc"));
  }

  public void testDocToFieldsSkipsInternalSolrFieldsAndKeepsTitleFirst() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    List<Map<String, String>> fields = SolrSupport.docToFields(mapper.readTree(
        "{\"title\":\"Java Developer\",\"_version_\":1,\"text\":\"noise\","
            + "\"company\":\"Intertec\",\"url\":\"http://example.com\",\"extra\":\"x\"}"));
    assertEquals("title", fields.get(0).get("name"));
    assertEquals("Java Developer", fields.get(0).get("value"));
    java.util.Set<String> names = new java.util.HashSet<String>();
    for (int i = 0; i < fields.size(); i++) {
      names.add(fields.get(i).get("name"));
    }
    assertTrue(names.contains("company"));
    assertTrue(names.contains("url"));
    assertTrue(names.contains("extra"));
    assertFalse(names.contains("_version_"));
    assertFalse(names.contains("text"));
    assertTrue(SolrSupport.skipRecordField("_root_"));
  }

  public void testDocToRowKeepsTableColumns() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    Map<String, Object> row = SolrSupport.docToRow(mapper.readTree(
        "{\"title\":\"Senior Core Java Developer\",\"company\":\"Intertec International\","
            + "\"location\":\"Costa Rica\",\"jobtype\":\"Full Time\"}"));
    assertEquals("Senior Core Java Developer", row.get("title"));
    assertEquals("Intertec International", row.get("company"));
    assertEquals("", row.get("url"));
    assertTrue(row.containsKey("postedDate"));
  }
}
