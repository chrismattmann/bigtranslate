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

public class TestLocationGeocoder extends TestCase {

  private LocationGeocoder geocoder;

  @Override
  protected void setUp() {
    geocoder = new LocationGeocoder();
  }

  public void testCountryFromTheTestdata() {
    LocationGeocoder.Coord coord = geocoder.geocode("Costa Rica");
    assertNotNull(coord);
    assertEquals(9.7489, coord.lat, 0.001);
    assertEquals(-83.7534, coord.lng, 0.001);
  }

  public void testAccentFolding() {
    LocationGeocoder.Coord mexico = geocoder.geocode("México");
    LocationGeocoder.Coord plain = geocoder.geocode("Mexico");
    assertNotNull(mexico);
    assertNotNull(plain);
    assertEquals(plain.lat, mexico.lat, 0.0001);
    assertEquals(plain.lng, mexico.lng, 0.0001);
  }

  public void testCityCountryStringUsesTheCountryWhenTheCityIsUnknown() {
    LocationGeocoder.Coord coord = geocoder.geocode("Unknown Town, Costa Rica");
    assertNotNull(coord);
    assertEquals(9.7489, coord.lat, 0.001);
  }

  public void testKnownCityWinsOnItsOwn() {
    LocationGeocoder.Coord coord = geocoder.geocode("Santo Domingo");
    assertNotNull(coord);
    assertEquals(18.4861, coord.lat, 0.001);
  }

  public void testEmptyAndPlaceholderValuesAreUnlocated() {
    assertNull(geocoder.geocode(null));
    assertNull(geocoder.geocode(""));
    assertNull(geocoder.geocode("   "));
    assertNull(geocoder.geocode("-"));
    assertNull(geocoder.geocode("n/a"));
    assertNull(geocoder.geocode("unknown"));
  }

  public void testNormalizeFoldsCaseAndAccents() {
    assertEquals("san jose", LocationGeocoder.normalize("San José"));
    assertEquals("republica dominicana",
        LocationGeocoder.normalize("República Dominicana"));
  }

  public void testParseableNumberRejectsEmptyAndZero() {
    assertFalse(LocationGeocoder.parseableNumber(null));
    assertFalse(LocationGeocoder.parseableNumber(""));
    assertFalse(LocationGeocoder.parseableNumber("0"));
    assertFalse(LocationGeocoder.parseableNumber("0.0"));
    assertTrue(LocationGeocoder.parseableNumber("9.7489"));
    assertTrue(LocationGeocoder.parseableNumber("-83.7534"));
  }

  public void testSpanishCountryAlias() {
    LocationGeocoder.Coord coord = geocoder.geocode("República Dominicana");
    assertNotNull(coord);
    assertEquals(18.7357, coord.lat, 0.001);
  }
}
