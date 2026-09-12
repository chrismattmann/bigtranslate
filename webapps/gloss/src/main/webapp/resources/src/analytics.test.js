// Licensed to the Apache Software Foundation (ASF) under one or more
// contributor license agreements.  See the NOTICE file distributed with
// this work for additional information regarding copyright ownership.
// The ASF licenses this file to You under the Apache License, Version 2.0
// (the "License"); you may not use this file except in compliance with
// the License.  You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  MIN_REGION_POSTINGS, SECTORS, SECTOR_FIELDS, growthRate, linearFit,
  monthLabel, opportunities, project, sectorCounts, sectorFacet, sectorQuery,
  sectorShares, shareSeries, wholeMonths, zone
} from './analytics.js'

test('a sector asks Solr for any of its words', () => {
  const s = { key: 'transport', words: ['Driver', 'Courier'] }
  assert.equal(sectorQuery(s, 'title_txt'), 'title_txt:(Driver OR Courier)')
})

test('every sector is asked for in one request', () => {
  const facet = sectorFacet('text')
  assert.equal(Object.keys(facet).length, SECTORS.length)
  SECTORS.forEach((s) => {
    assert.equal(facet[s.key].type, 'query')
    assert.ok(facet[s.key].q.startsWith('text:('))
  })
})

test('extra facets ride along with the sectors', () => {
  const facet = sectorFacet('text', { months: { type: 'range' } })
  assert.equal(facet.months.type, 'range')
  assert.equal(Object.keys(facet).length, SECTORS.length + 1)
})

test('a missing sector counts zero rather than undefined', () => {
  // Solr leaves sub-facets off a bucket with no documents, and a chart that
  // plots undefined draws nothing while looking like it drew something.
  const counts = sectorCounts({ office: { count: 12 } })
  assert.equal(counts.office, 12)
  assert.equal(counts.retail, 0)
  assert.equal(sectorCounts(null).office, 0)
  assert.equal(sectorCounts(undefined).medical, 0)
})

test('shares are of the sector total, so places compare', () => {
  const shares = sectorShares({ office: 30, retail: 10 })
  assert.equal(shares.total, 40)
  assert.equal(shares.office, 0.75)
  assert.equal(shares.retail, 0.25)
})

test('a place with no sector postings has no shares and no zone', () => {
  const shares = sectorShares({})
  assert.equal(shares.total, 0)
  assert.equal(shares.office, 0)
  assert.equal(zone({}).key, null)
})

test('Q14: the zone is the leading sector', () => {
  const z = zone({ office: 50, retail: 30, it: 20 })
  assert.equal(z.key, 'office')
  assert.equal(z.share, 0.5)
})

test('Q14: the margin says how much of a classification it is', () => {
  const clear = zone({ office: 90, retail: 10 })
  const close = zone({ office: 51, retail: 49 })
  assert.ok(clear.margin > 0.7)
  assert.ok(close.margin < 0.05,
    'a two point lead must not read like a classification')
})

test('a fit recovers a line it was given', () => {
  const fit = linearFit([{ x: 0, y: 1 }, { x: 1, y: 3 }, { x: 2, y: 5 }])
  assert.equal(fit.slope, 2)
  assert.equal(fit.intercept, 1)
  assert.equal(fit.r2, 1)
})

test('a flat series has no slope and no fit to report', () => {
  const fit = linearFit([{ x: 0, y: 4 }, { x: 1, y: 4 }, { x: 2, y: 4 }])
  assert.equal(fit.slope, 0)
  assert.equal(fit.r2, 0)
})

test('scatter fits worse than a line, and says so', () => {
  const noisy = linearFit([
    { x: 0, y: 10 }, { x: 1, y: 1 }, { x: 2, y: 9 }, { x: 3, y: 2 }
  ])
  assert.ok(noisy.r2 < 0.3, 'r2 was ' + noisy.r2)
})

test('Q1: a rising series projects upward', () => {
  const { projected, fit } = project([10, 20, 30, 40], 2)
  assert.equal(projected.length, 2)
  assert.equal(projected[0], 50)
  assert.equal(projected[1], 60)
  assert.equal(fit.r2, 1)
})

test('Q1: a projection never goes below zero', () => {
  // A steep enough decline crosses the axis within the projected window, and
  // a negative number of job postings is not a claim worth drawing.
  const { projected } = project([100, 60, 20], 3)
  projected.forEach((v) => assert.ok(v >= 0, 'projected ' + v))
})

test('growth is relative, so a small sector can out-grow a large one', () => {
  const small = growthRate([1000, 1050, 1100, 1150])
  const large = growthRate([100000, 101000, 102000, 103000])
  assert.ok(small > large,
    'a raw slope would pick the large sector every time')
})

test('growth of nothing is zero rather than infinite', () => {
  assert.equal(growthRate([]), 0)
  assert.equal(growthRate([0, 0, 0]), 0)
})

test('Q5: an opportunity needs both a gap and national growth', () => {
  const national = { it: 0.30, retail: 0.30 }
  const growth = { it: 0.05, retail: -0.05 }
  const regions = [{
    name: 'Lima', total: 50000, counts: { it: 10, retail: 10, office: 80 }
  }]
  const found = opportunities(regions, national, growth)
  const keys = found.map((o) => o.sector)
  assert.ok(keys.includes('it'), 'a growing sector with a gap is an opening')
  assert.ok(!keys.includes('retail'), 'a shrinking sector is not an opening')
})

test('Q5: a sector already over-represented locally is not an opening', () => {
  const found = opportunities(
    [{ name: 'Lima', total: 50000, counts: { it: 90, office: 10 } }],
    { it: 0.10 }, { it: 0.5 })
  assert.equal(found.filter((o) => o.sector === 'it').length, 0)
})

test('Q5: a region too small to mean anything is left out', () => {
  // Twelve postings give a 100% shortfall in every sector and would lead
  // the table on arithmetic alone.
  const tiny = [{ name: 'Somewhere', total: 12, counts: { office: 12 } }]
  assert.deepEqual(opportunities(tiny, { it: 0.3 }, { it: 0.4 }), [])
  const big = [{
    name: 'Somewhere', total: MIN_REGION_POSTINGS, counts: { office: 12 }
  }]
  assert.ok(opportunities(big, { it: 0.3 }, { it: 0.4 }).length > 0)
})

test('Q5: the strongest opening is first', () => {
  const found = opportunities(
    [{ name: 'A', total: 90000, counts: { office: 100 } },
     { name: 'B', total: 90000, counts: { office: 90, it: 10 } }],
    { it: 0.4 }, { it: 0.2 })
  assert.equal(found[0].region, 'A', 'A has the larger gap')
  assert.ok(found[0].score >= found[found.length - 1].score)
})

test('months are labelled with the year in full', () => {
  // "Aug 12 to Nov 13" reads as a day and a month, and this corpus runs
  // across a year boundary.
  assert.equal(monthLabel('2012-07-01T00:00:00Z'), 'Jul 2012')
  assert.equal(monthLabel('2013-12-01T00:00:00Z'), 'Dec 2013')
  assert.equal(monthLabel(''), '')
  assert.equal(monthLabel(null), '')
})

test('partial months at the ends are dropped', () => {
  // Collection started on 2012-07-31 and stopped on 2013-12-13, so the first
  // bucket holds one day and the last thirteen. Left in, a trend reads the
  // end of the scrape as a collapse in hiring.
  const buckets = [
    { val: '2012-07-01T00:00:00Z', count: 4410 },
    { val: '2012-08-01T00:00:00Z', count: 980804 },
    { val: '2012-09-01T00:00:00Z', count: 2604364 },
    { val: '2012-10-01T00:00:00Z', count: 2700000 },
    { val: '2013-12-01T00:00:00Z', count: 234620 }
  ]
  const kept = wholeMonths(buckets)
  assert.equal(kept.length, 3)
  assert.equal(kept[0].val, '2012-08-01T00:00:00Z')
  assert.equal(kept[kept.length - 1].val, '2012-10-01T00:00:00Z')
})

test('a series of whole months is left alone', () => {
  const buckets = [
    { val: 'a', count: 1000 }, { val: 'b', count: 1100 },
    { val: 'c', count: 1050 }, { val: 'd', count: 1020 }
  ]
  assert.equal(wholeMonths(buckets).length, 4)
})

test('too few buckets to judge are left alone', () => {
  assert.equal(wholeMonths([{ val: 'a', count: 1 }]).length, 1)
  assert.deepEqual(wholeMonths([]), [])
  assert.deepEqual(wholeMonths(null), [])
})

test('the field a sector is matched against is named, not assumed', () => {
  // "42.9% of postings are in a sector" means something different for the
  // catch-all text field than for a tokenised title, so the panels have to
  // be able to say which they used.
  assert.equal(SECTOR_FIELDS.precise, 'title_txt')
  assert.equal(SECTOR_FIELDS.broad, 'text')
})

test('sector words are English, because the pipeline translated them', () => {
  const words = SECTORS.flatMap((s) => s.words)
  assert.ok(words.includes('Driver'))
  assert.ok(words.length > 40, 'too few words to catch a long tail')
  words.forEach((w) => assert.match(w, /^[A-Z][A-Za-z]+$/, w))
})


test('a sector series is its share of each month, not its count', () => {
  // Collection wound down over this corpus: postings per month fall about 7%
  // a month, so every sector's raw count falls with it and every sector reads
  // as declining. Measured that way all nine were negative, which is the
  // scraper stopping rather than the job market doing anything.
  const buckets = [
    { count: 1000, it: { count: 100 } },
    { count: 500, it: { count: 75 } }
  ]
  assert.deepEqual(shareSeries(buckets, 'it'), [0.1, 0.15])
})

test('a sector holding its share through a collapse in collection is flat', () => {
  const buckets = [
    { count: 4000, it: { count: 400 } },
    { count: 2000, it: { count: 200 } },
    { count: 1000, it: { count: 100 } }
  ]
  assert.equal(growthRate(shareSeries(buckets, 'it')), 0,
    'a constant share must not read as decline')
  assert.ok(growthRate([400, 200, 100]) < 0,
    'the raw counts do read as decline, which is the bug')
})

test('a month with nothing in it contributes no share', () => {
  assert.deepEqual(shareSeries([{ count: 0 }], 'it'), [0])
  assert.deepEqual(shareSeries([{ count: 10 }], 'it'), [0])
  assert.deepEqual(shareSeries(null, 'it'), [])
})


test('every sector has a short form for a crowded axis', () => {
  // "Food and hospitality" across an axis of nine columns has to be rotated
  // to fit, and a rotated label runs diagonally into whatever is above it.
  SECTORS.forEach((s) => {
    assert.ok(s.short, s.key + ' has no short label')
    assert.ok(s.short.length <= 12,
      s.short + ' is too long to sit flat on the axis')
    assert.ok(s.label.length >= s.short.length)
  })
})
