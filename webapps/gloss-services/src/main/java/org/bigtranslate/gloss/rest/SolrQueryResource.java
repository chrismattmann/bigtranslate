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

import java.util.Arrays;
import java.util.List;
import java.util.logging.Logger;

import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import javax.ws.rs.Produces;
import javax.ws.rs.core.Context;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.UriInfo;

import org.bigtranslate.gloss.SolrSupport;

/**
 * Read-only passthrough to Solr so the browser stays same-origin. Solr is
 * a standalone process on 8983; Gloss must not talk to it across origins.
 * Only select is exposed.
 */
@Path("/solr")
@Produces(MediaType.APPLICATION_JSON)
public class SolrQueryResource {

  private static final Logger LOG = Logger.getLogger(SolrQueryResource.class.getName());
  private static final List<String> CORES = Arrays.asList("bigtranslate");

  @GET
  @Path("/{core}/select")
  public String select(@PathParam("core") String core, @Context UriInfo uriInfo) {
    if (!CORES.contains(core)) {
      LOG.warning("Refusing to proxy a query for unknown core: [" + core + "]");
      return "{\"error\":\"unknown core\"}";
    }
    try {
      return new SolrSupport().select(uriInfo.getQueryParameters());
    } catch (Exception e) {
      LOG.warning("Unable to query Solr: " + e.getLocalizedMessage());
      return "{\"error\":\"Unable to reach Solr\"}";
    }
  }
}
