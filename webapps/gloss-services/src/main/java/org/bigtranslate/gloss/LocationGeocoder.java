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

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Collections;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Turns a posting's location string into a lat/lng for the density map.
 *
 * The Computrabajo TSVs usually leave {@code latitude}/{@code longitude}
 * empty and put a country or city name in {@code location} ("Costa Rica",
 * "Santo Domingo"). Faceting Solr and looking those names up here is how
 * Gloss draws 190 million rows without dumping them.
 */
public class LocationGeocoder {

  public static final class Coord {
    public final double lat;
    public final double lng;
    public final String matched;

    public Coord(double lat, double lng, String matched) {
      this.lat = lat;
      this.lng = lng;
      this.matched = matched;
    }
  }

  private final Map<String, Coord> lookup;

  public LocationGeocoder() {
    this(loadDefault());
  }

  LocationGeocoder(Map<String, Coord> lookup) {
    this.lookup = lookup;
  }

  public Coord geocode(String location) {
    if (location == null) {
      return null;
    }
    String trimmed = location.trim();
    if (trimmed.isEmpty() || "-".equals(trimmed) || "n/a".equalsIgnoreCase(trimmed)
        || "null".equalsIgnoreCase(trimmed) || "unknown".equalsIgnoreCase(trimmed)) {
      return null;
    }
    Coord exact = lookup.get(normalize(trimmed));
    if (exact != null) {
      return exact;
    }
    // "San José, Costa Rica" -> try the whole string, then city, then country.
    String[] parts = trimmed.split("[,/|;]+");
    if (parts.length > 1) {
      for (int i = 0; i < parts.length; i++) {
        Coord part = lookup.get(normalize(parts[i]));
        if (part != null) {
          return part;
        }
      }
    }
    return null;
  }

  public static boolean parseableNumber(String value) {
    if (value == null) {
      return false;
    }
    String t = value.trim();
    if (t.isEmpty() || "0".equals(t) || "0.0".equals(t)) {
      return false;
    }
    try {
      Double.parseDouble(t);
      return true;
    } catch (NumberFormatException e) {
      return false;
    }
  }

  public static Double parseDouble(String value) {
    if (!parseableNumber(value)) {
      return null;
    }
    return Double.valueOf(value.trim());
  }

  static String normalize(String value) {
    String n = Normalizer.normalize(value.trim(), Normalizer.Form.NFD);
    StringBuilder b = new StringBuilder(n.length());
    for (int i = 0; i < n.length(); i++) {
      char c = n.charAt(i);
      if (Character.getType(c) != Character.NON_SPACING_MARK) {
        b.append(c);
      }
    }
    return b.toString().toLowerCase(Locale.ROOT).replaceAll("\\s+", " ").trim();
  }

  static Map<String, Coord> loadDefault() {
    InputStream in = LocationGeocoder.class.getResourceAsStream(
        "country-centroids.tsv");
    if (in == null) {
      throw new IllegalStateException("country-centroids.tsv is missing from the classpath");
    }
    try {
      return load(in);
    } catch (IOException e) {
      throw new IllegalStateException("Unable to read country-centroids.tsv", e);
    }
  }

  static Map<String, Coord> load(InputStream in) throws IOException {
    Map<String, Coord> map = new HashMap<String, Coord>();
    BufferedReader reader = new BufferedReader(
        new InputStreamReader(in, StandardCharsets.UTF_8));
    try {
      String line;
      while ((line = reader.readLine()) != null) {
        if (line.isEmpty() || line.charAt(0) == '#') {
          continue;
        }
        String[] cols = line.split("\t");
        if (cols.length < 3) {
          continue;
        }
        String name = cols[0].trim();
        double lat = Double.parseDouble(cols[1].trim());
        double lng = Double.parseDouble(cols[2].trim());
        map.put(normalize(name), new Coord(lat, lng, name));
      }
    } finally {
      reader.close();
    }
    return Collections.unmodifiableMap(map);
  }
}
