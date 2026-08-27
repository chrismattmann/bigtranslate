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

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.Logger;

import javax.ws.rs.Consumes;
import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;

import org.bigtranslate.gloss.ProcessBtWrapper;

/**
 * Pipeline control. Translate wraps {@code bin/bigtranslate translate} the
 * same way Proteus wraps {@code bin/drat}. The CLI remains the other way
 * to start a run.
 */
@Path("/bt")
@Produces(MediaType.APPLICATION_JSON)
public class BtRestResource {

  private static final Logger LOG = Logger.getLogger(BtRestResource.class.getName());
  private final ProcessBtWrapper wrapper;

  public BtRestResource() {
    this.wrapper = ProcessBtWrapper.getInstance();
  }

  BtRestResource(ProcessBtWrapper wrapper) {
    this.wrapper = wrapper;
  }

  @POST
  @Path("/translate")
  @Consumes(MediaType.APPLICATION_JSON)
  public Response translate(BtRequestWrapper body) {
    try {
      String path = body == null ? null : body.path;
      String exclude = body == null ? null : body.exclude;
      wrapper.translate(path, exclude);
      return Response.ok(wrapper.snapshot()).build();
    } catch (Exception e) {
      LOG.warning("translate failed: " + e.getLocalizedMessage());
      return error(e);
    }
  }

  @POST
  @Path("/reset")
  public Response reset() {
    try {
      wrapper.reset();
      return Response.ok(wrapper.snapshot()).build();
    } catch (Exception e) {
      LOG.warning("reset failed: " + e.getLocalizedMessage());
      return error(e);
    }
  }

  @GET
  @Path("/status")
  public Map<String, Object> status() {
    return wrapper.snapshot();
  }

  @GET
  @Path("/currentpath")
  @Produces(MediaType.TEXT_PLAIN)
  public String currentPath() {
    String path = wrapper.getPath();
    return path == null ? "" : path;
  }

  @GET
  @Path("/log")
  @Produces(MediaType.TEXT_PLAIN)
  public String log() {
    return ProcessBtWrapper.readLogTail(64 * 1024);
  }

  private static Response error(Exception e) {
    Map<String, Object> body = new LinkedHashMap<String, Object>();
    body.put("error", e.getLocalizedMessage());
    return Response.status(Response.Status.BAD_REQUEST).entity(body).build();
  }
}
