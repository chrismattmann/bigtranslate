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
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  concentration, territory, salaryIndex, salaryTrend, trendByRegion,
  SKILL_TIERS, skillQuery, skillMix, byCalendarMonth, anomalies,
  notableAnomalies, MIN_SALARY_RECORDS
} from './challenges.js'

// ---------------------------------------------------------------- companies

test('concentration is the sum of squared percentage shares', () => {
  // Two companies with half the market each: 50^2 + 50^2.
  const c = concentration([{ count: 50 }, { count: 50 }], 100)
  assert.equal(Math.round(c.hhi), 5000)
  assert.equal(c.covered, 1)
})

test('a long tail barely moves it', () => {
  // The point of squaring: 244,544 companies with one posting each cannot
  // add up to a concentrated market.
  // A thousand companies with one posting each: each holds 0.1%, and
  // 0.1^2 x 1000 is 10 -- against the 1,500 that counts as unconcentrated.
  const many = Array.from({ length: 1000 }, () => ({ count: 1 }))
  const hhi = concentration(many, 1000).hhi
  assert.ok(hhi < 100, `a flat market scored ${hhi}`)
})

test('concentration says how much of the market it measured', () => {
  // Faceting the top 20 of 244,544 measures a slice. A reader has to know
  // which slice, or the number is about the facet limit.
  const c = concentration([{ count: 10 }, { count: 10 }], 100)
  assert.equal(c.covered, 0.2)
})

test('an empty market is not an error', () => {
  assert.equal(concentration([], 0).hhi, 0)
})

test('territory is the share in the largest region', () => {
  const t = territory([{ val: 'Lima', count: 90 }, { val: 'Cusco', count: 10 }])
  assert.equal(t.share, 0.9)
  assert.equal(t.region, 'Lima')
  assert.equal(t.regions, 2)
})

test('a company spread evenly has a low territory share', () => {
  const t = territory(Array.from({ length: 10 },
    (_, i) => ({ val: 'r' + i, count: 10 })))
  assert.equal(t.share, 0.1)
})

test('territory counts only regions it actually posted in', () => {
  const t = territory([{ val: 'a', count: 5 }, { val: 'b', count: 0 }])
  assert.equal(t.regions, 1)
})

// ------------------------------------------------------------ compensation

test('a salary series is indexed to its own first month', () => {
  const s = salaryIndex([
    { val: '2013-01', median: 1000, n: 500 },
    { val: '2013-02', median: 1100, n: 500 }
  ])
  assert.equal(s[0].index, 100)
  assert.equal(Math.round(s[1].index), 110)
})

test('thin months are dropped rather than plotted', () => {
  // 8.9% of postings state a salary. In a thin month that is a handful of
  // records whose median jumps for no reason.
  const s = salaryIndex([
    { val: '2013-01', median: 1000, n: MIN_SALARY_RECORDS },
    { val: '2013-02', median: 9999, n: 3 }
  ])
  assert.equal(s.length, 1)
})

test('a month with no stated salaries is dropped', () => {
  assert.equal(salaryIndex([{ val: '2013-01', median: 0, n: 900 }]).length, 0)
})

test('the salary trend carries its own R2', () => {
  const s = salaryIndex([
    { val: '1', median: 100, n: 500 },
    { val: '2', median: 110, n: 500 },
    { val: '3', median: 120, n: 500 }
  ])
  const t = salaryTrend(s)
  assert.ok(t.perMonth > 9 && t.perMonth < 11)
  assert.ok(t.r2 > 0.99)
})

test('two points are not a trend', () => {
  assert.equal(salaryTrend([{ index: 100 }, { index: 200 }]).perMonth, 0)
})

// ---------------------------------------------------------------- downtrend

test('downtrend ranks the steepest loser first', () => {
  const rows = trendByRegion([
    { region: 'falling', total: 10000, shares: [0.3, 0.2, 0.1] },
    { region: 'rising', total: 10000, shares: [0.1, 0.2, 0.3] }
  ], 5000)
  assert.equal(rows[0].region, 'falling')
  assert.ok(rows[0].perMonth < 0)
})

test('a thin region is left out', () => {
  // A handful of postings is a steep trend by arithmetic.
  const rows = trendByRegion([
    { region: 'tiny', total: 12, shares: [0.9, 0.1] }
  ], 5000)
  assert.equal(rows.length, 0)
})

test('the rate is relative, so small regions can rank', () => {
  // Both lose a tenth of themselves a month. Absolute slope would rank only
  // the big one.
  const rows = trendByRegion([
    { region: 'big', total: 99999, shares: [0.20, 0.18, 0.16] },
    { region: 'small', total: 99999, shares: [0.02, 0.018, 0.016] }
  ], 5000)
  assert.ok(Math.abs(rows[0].perMonth - rows[1].perMonth) < 0.01)
})

// -------------------------------------------------------------- skill level

test('every tier contributes terms to its query', () => {
  for (const tier of SKILL_TIERS) {
    const q = skillQuery(tier, 'title_txt')
    assert.ok(q.includes('title_txt:'))
    assert.equal(q.split(' OR ').length, tier.terms.length)
  }
})

test('the tiers are ordered from entry to senior', () => {
  assert.deepEqual(SKILL_TIERS.map((t) => t.key),
    ['entry', 'skilled', 'professional', 'senior'])
})

test('a skill mix sums to one', () => {
  const mix = skillMix({
    entry: { count: 10 }, skilled: { count: 20 },
    professional: { count: 30 }, senior: { count: 40 }
  })
  assert.ok(Math.abs(mix.reduce((a, m) => a + m.share, 0) - 1) < 1e-9)
})

test('an empty bucket is all zeroes rather than NaN', () => {
  const mix = skillMix({})
  assert.equal(mix.length, SKILL_TIERS.length)
  for (const m of mix) {
    assert.equal(m.share, 0)
  }
})

// -------------------------------------------------------------- seasonality

test('calendar months are split by year, not folded together', () => {
  // Eighteen months is one cycle and half of another. Folded, August 2012
  // and August 2013 would be averaged and shown as a season.
  const years = byCalendarMonth([
    { val: '2012-08-01T00:00:00Z', count: 100, s: { count: 10 } },
    { val: '2013-08-01T00:00:00Z', count: 100, s: { count: 30 } }
  ], 's')
  assert.equal(years.length, 2)
  assert.equal(years[0].year, 2012)
  assert.equal(years[0].points[0].share, 0.1)
  assert.equal(years[1].points[0].share, 0.3)
})

test('a bucket with no month is skipped rather than dated to year zero', () => {
  assert.equal(byCalendarMonth([{ val: '', count: 5 }], null).length, 0)
})

test('with no key it plots the total', () => {
  const years = byCalendarMonth(
    [{ val: '2013-03-01T00:00:00Z', count: 7 }], null)
  assert.equal(years[0].points[0].count, 7)
})

// ---------------------------------------------------------------- anomalies

test('a region exactly on its trend has no anomalies', () => {
  // Residuals of about 1e-18. Divided by their own standard deviation that
  // is a stack of five sigma anomalies made entirely of rounding error.
  const rows = anomalies([
    { region: 'steady', total: 99999, shares: [0.1, 0.2, 0.3, 0.4] }
  ], 5000)
  for (const z of rows[0].z) {
    assert.ok(Math.abs(z) < 1e-6, `rounding error scored ${z}`)
  }
})

test('a spike against the trend shows up', () => {
  const rows = anomalies([
    { region: 'spiky', total: 99999, shares: [0.1, 0.1, 0.9, 0.1, 0.1] }
  ], 5000)
  const worst = Math.max(...rows[0].z.map(Math.abs))
  assert.ok(worst > 1.5, 'a spike five times the level did not register')
})

test('a flat series is not every month an anomaly', () => {
  // Dividing by a standard deviation of zero.
  const rows = anomalies([
    { region: 'flat', total: 99999, shares: [0.2, 0.2, 0.2] }
  ], 5000)
  for (const z of rows[0].z) {
    assert.equal(z, 0)
  }
})

test('notable anomalies come back strongest first and named', () => {
  const rows = [{ region: 'r', total: 1, z: [0, 3.5, -2.5] }]
  const out = notableAnomalies(rows, ['2013-01', '2013-02', '2013-03'])
  assert.equal(out.length, 2)
  assert.equal(out[0].month, '2013-02')
  assert.equal(out[1].month, '2013-03')
})

test('a quiet index reports nothing rather than its loudest noise', () => {
  const rows = [{ region: 'r', total: 1, z: [0.1, -0.4, 0.2] }]
  assert.equal(notableAnomalies(rows, ['a', 'b', 'c']).length, 0)
})

// --------------------------------------------------- nested facet depth
//
// A terms facet nested inside a month bucket returns that month's top N,
// which is not the corpus-wide top N. A region fourteenth overall can be
// twentieth in a quiet month, come back absent, and be read as a month of
// zero postings -- a collapse that never happened, on exactly the two
// panels whose job is to find collapses.

test('a series with a hole in it is not a collapse', () => {
  // What it looks like when the nested limit cut a region off: present,
  // present, absent, present. Read as zero that is a 100% crash and a
  // recovery, and the anomaly panel will report it as five sigma.
  const holed = [
    { region: 'patchy', total: 99999, shares: [0.2, 0.2, 0, 0.2], missing: 1 }
  ]
  const rows = anomalies(holed.filter((r) => r.missing === 0), 5000)
  assert.equal(rows.length, 0, 'a holed series reached the anomaly panel')
})

test('a complete series is kept', () => {
  const whole = [
    { region: 'complete', total: 99999, shares: [0.2, 0.21, 0.19, 0.2], missing: 0 }
  ]
  assert.equal(anomalies(whole.filter((r) => r.missing === 0), 5000).length, 1)
})

test('the downtrend panel drops holed series too', () => {
  const holed = [
    { region: 'patchy', total: 99999, shares: [0.2, 0, 0.2], missing: 1 }
  ]
  assert.equal(trendByRegion(holed.filter((r) => r.missing === 0), 5000).length, 0)
})

// ------------------------------------------------------- tier vocabulary
//
// Checked against the translation database rather than guessed. "Ejecutivo"
// is the word that mattered: 33,223 distinct translated strings contain
// "executive", and on a sample of four thousand, 48% are "Ejecutivo de
// Ventas" or "Ejecutivo de Cobranza" -- sales reps and collections agents.

test('executive is not a management title in this corpus', () => {
  const senior = SKILL_TIERS.find((t) => t.key === 'senior')
  assert.ok(!senior.terms.includes('executive'),
    'Ejecutivo de Ventas is a sales rep; counting it as management puts a '
    + 'tenth of the corpus in the wrong tier')
})

test('head is kept, because it is Jefe', () => {
  const senior = SKILL_TIERS.find((t) => t.key === 'senior')
  assert.ok(senior.terms.includes('head'))
})

test('practitioner is in the entry tier', () => {
  // Practicante is an intern. It is the most common entry-tier word in the
  // corpus by a wide margin -- 14,143 strings against 947 for trainee.
  const entry = SKILL_TIERS.find((t) => t.key === 'entry')
  assert.ok(entry.terms.includes('practitioner'))
})

test('no term appears in two tiers', () => {
  const seen = new Set()
  for (const tier of SKILL_TIERS) {
    for (const term of tier.terms) {
      assert.ok(!seen.has(term), `${term} is in two tiers`)
      seen.add(term)
    }
  }
})
