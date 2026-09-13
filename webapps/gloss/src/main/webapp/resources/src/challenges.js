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
//
// The arithmetic behind the second half of the challenge questions.
//
// The employment set ships twenty challenges: fifteen analytic and five
// visual. analytics.js answers six of them. These are the rest of the ones
// this index can answer on its own -- companies, compensation, downtrend,
// skill level, fill speed, transport, seasonality and anomalies.
//
// Kept apart from the drawing for the reason the first half is: every number
// on the page should be checkable without a browser, and a claim about a
// labour market is worth more scrutiny than a claim about a rectangle.

import { linearFit } from './analytics.js'

// ---------------------------------------------------------------- companies

/**
 * How concentrated a market is, on the Herfindahl-Hirschman index.
 *
 * The sum of squared percentage shares. Competition authorities read it as
 * below 1,500 unconcentrated, 1,500 to 2,500 moderate, above 2,500
 * concentrated -- so it turns "are there territories?" into a number rather
 * than an impression of a chart.
 *
 * Computed over the companies given, not over all 244,544 of them: the tail
 * is one posting each and contributes almost nothing to the sum of squares,
 * but including it would make the total depend on how deep the facet went
 * rather than on the market. Which is why `of` is the real total and the
 * result says what fraction of it was measured.
 */
export function concentration(companies, of) {
  const total = of || companies.reduce((a, c) => a + (c.count || 0), 0)
  if (!total) {
    return { hhi: 0, covered: 0, top: 0 }
  }
  let hhi = 0
  let counted = 0
  for (const c of companies) {
    const share = (c.count || 0) / total
    hhi += (share * 100) * (share * 100)
    counted += c.count || 0
  }
  return {
    hhi,
    covered: counted / total,
    top: companies.length ? (companies[0].count || 0) / total : 0
  }
}

/**
 * How much of a company's hiring sits in its single largest region.
 *
 * The challenge asks whether there are territories. A staffing agency that
 * posts everywhere and one that posts in a single city are the same size in
 * a bar chart and completely different businesses; this separates them.
 *
 * 1 is a company that posts in one region only. Near 1/regions is one spread
 * evenly. Reported alongside the count, because a company with four postings
 * is territorial by arithmetic rather than by strategy.
 */
export function territory(regions) {
  const counts = regions.map((r) => r.count || 0)
  const total = counts.reduce((a, b) => a + b, 0)
  if (!total) {
    return { share: 0, region: '', total: 0, regions: 0 }
  }
  let best = 0
  for (let i = 1; i < counts.length; i += 1) {
    if (counts[i] > counts[best]) {
      best = i
    }
  }
  return {
    share: counts[best] / total,
    region: regions[best].val,
    total,
    regions: counts.filter((c) => c > 0).length
  }
}

// ------------------------------------------------------------ compensation

/**
 * A salary series indexed to its own first month.
 *
 * Levels cannot be compared across these four countries: a Colombian peso
 * and a Peruvian sol are three orders of magnitude apart, so a chart of raw
 * medians is a chart of which country posted most that month. Indexed to
 * 100 at the first month, each country is compared only against itself,
 * which is what "how are compensations changing over time" actually asks.
 *
 * Months with too few stated salaries are dropped rather than plotted: about
 * 8.9% of postings quote a figure, and in a thin region that can be a
 * handful of records whose median jumps around for no reason.
 */
export const MIN_SALARY_RECORDS = 200

export function salaryIndex(buckets, minRecords = MIN_SALARY_RECORDS) {
  const usable = buckets.filter(
    (b) => (b.n || 0) >= minRecords && (b.median || 0) > 0)
  if (!usable.length) {
    return []
  }
  const base = usable[0].median
  return usable.map((b) => ({
    month: b.val,
    index: (b.median / base) * 100,
    median: b.median,
    n: b.n
  }))
}

/**
 * What an indexed salary series did, as a monthly rate with its fit.
 *
 * The same least squares line the sector trends use, and with the same
 * limits: no seasonality, no saturation, eighteen points at most. The R2 is
 * returned so the panel can print it rather than imply a confidence the fit
 * does not have.
 */
export function salaryTrend(series) {
  if (series.length < 3) {
    return { perMonth: 0, r2: 0, n: series.length }
  }
  const fit = linearFit(series.map((p, i) => ({ x: i, y: p.index })))
  return { perMonth: fit.slope, r2: fit.r2, n: series.length }
}

// ---------------------------------------------------------------- downtrend

/**
 * Regions losing share, worst first.
 *
 * The mirror of the openings panel, and it needs to be measured the same
 * way. Raw counts fall everywhere because the scrape wound down about 7% a
 * month, so a chart of counts marks every region as declining and says
 * nothing. Share of the month removes that: a region declining here is one
 * losing ground to the other regions, not one caught in the collection
 * tailing off.
 */
export function trendByRegion(regionSeries, minPostings) {
  const out = []
  for (const region of regionSeries) {
    if ((region.total || 0) < minPostings) {
      continue
    }
    const points = region.shares.map((y, x) => ({ x, y }))
    const fit = linearFit(points)
    const mean = points.reduce((a, p) => a + p.y, 0) / (points.length || 1)
    out.push({
      region: region.region,
      total: region.total,
      // Relative, so a region holding 2% and losing a tenth of it ranks with
      // one holding 20% and losing a tenth of that. Absolute slope would
      // only ever rank the biggest regions.
      perMonth: mean ? fit.slope / mean : 0,
      r2: fit.r2,
      mean
    })
  }
  return out.sort((a, b) => a.perMonth - b.perMonth)
}

// -------------------------------------------------------------- skill level

/**
 * Four tiers, inferred from words in the translated job title.
 *
 * The corpus has no education column. The challenge asks for one anyway, so
 * this reads the title, which the pipeline translated into English and which
 * is therefore short enough to match on. It is an inference and the panel
 * says so: a "Manager" in a corner shop and a "Manager" in a bank are one
 * tier here.
 *
 * Ordered, because the point is a distribution rather than a set of labels.
 */
export const SKILL_TIERS = [
  {
    key: 'entry',
    label: 'Entry and training',
    short: 'Entry',
    terms: ['intern', 'internship', 'trainee', 'apprentice', 'practitioner',
            'student', 'beginner']
  },
  {
    key: 'skilled',
    label: 'Skilled and assistant',
    short: 'Skilled',
    terms: ['assistant', 'technician', 'operator', 'clerk', 'secretary',
            'auxiliary', 'helper']
  },
  {
    key: 'professional',
    label: 'Professional and graduate',
    short: 'Professional',
    terms: ['engineer', 'analyst', 'graduate', 'accountant', 'lawyer',
            'architect', 'doctor', 'nurse', 'developer', 'designer']
  },
  {
    key: 'senior',
    label: 'Management and senior',
    short: 'Senior',
    // No 'executive'. It is the third most common word in this tier's
    // vocabulary -- 33,223 distinct translated strings -- and on a sample of
    // four thousand of them 48% are "Ejecutivo de Ventas", "Ejecutivo de
    // Cobranza" and the like: sales representatives and collections agents,
    // which in Latin America is what Ejecutivo usually means. Counting them
    // as management would have put a tenth of the corpus in the wrong tier
    // and made every country look top heavy. Dropped rather than guessed:
    // this panel is already an inference, and an inference that is wrong
    // half the time is not one worth making.
    //
    // 'head' stays. It is Jefe -- Jefe de Planta, Jefe de Produccion, Jefe
    // de Enfermeria -- and on the same sample it is supervisory throughout.
    terms: ['manager', 'director', 'head', 'chief', 'supervisor',
            'coordinator', 'president']
  }
]

export function skillQuery(tier, field) {
  return tier.terms.map((t) => `${field}:${t}`).join(' OR ')
}

export function skillFacet(field) {
  return SKILL_TIERS.reduce((acc, tier) => {
    acc[tier.key] = { type: 'query', q: skillQuery(tier, field) }
    return acc
  }, {})
}

/**
 * A tier mix as shares that sum to one.
 *
 * A title can match two tiers -- "Assistant Manager" is both -- so the counts
 * overlap and their sum is not the number of postings. Normalised against
 * that sum rather than against the bucket total, so the bars fill the width
 * and the panel is honest that it is showing a mix rather than a partition.
 */
export function skillMix(bucket) {
  const counts = SKILL_TIERS.map(
    (t) => (bucket[t.key] && bucket[t.key].count) || 0)
  const total = counts.reduce((a, b) => a + b, 0)
  if (!total) {
    return SKILL_TIERS.map((t) => ({ key: t.key, share: 0, count: 0 }))
  }
  return SKILL_TIERS.map((t, i) => ({
    key: t.key,
    share: counts[i] / total,
    count: counts[i]
  }))
}

// -------------------------------------------------------------- seasonality

export const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * A series per calendar year, so the reader can see how little there is.
 *
 * The corpus covers eighteen months: one full cycle and half of another.
 * Folding that into a single "seasonal" curve would average August 2012 with
 * August 2013 and present the result as a season, which on two observations
 * it is not. Drawn as one line per year instead, the reader sees two lines
 * that either agree or do not, and sees that one of them is half a year.
 */
export function byCalendarMonth(buckets, key) {
  const years = new Map()
  for (const bucket of buckets) {
    const iso = bucket.val || ''
    const year = Number(iso.slice(0, 4))
    const month = Number(iso.slice(5, 7))
    if (!year || !month) {
      continue
    }
    const total = bucket.count || 0
    const part = key
      ? ((bucket[key] && bucket[key].count) || 0)
      : total
    if (!years.has(year)) {
      years.set(year, [])
    }
    years.get(year).push({
      month,
      share: total ? part / total : 0,
      count: part,
      total
    })
  }
  return Array.from(years.entries())
    .map(([year, points]) => ({
      year,
      points: points.sort((a, b) => a.month - b.month)
    }))
    .sort((a, b) => a.year - b.year)
}

// ---------------------------------------------------------------- anomalies

/**
 * How far each month sits from what that region's own trend predicts.
 *
 * "Discover temporal or geospatial anomalies" needs a definition of normal.
 * Normal here is the region's own least squares line through its share of
 * the month: a residual in standard deviations, so a region holding 20% and
 * one holding 2% are on the same scale and a spike in the small one is not
 * drowned by noise in the big one.
 *
 * Against its own trend rather than against the other regions, because the
 * whole corpus is declining and a common decline is not an anomaly.
 */
export const ANOMALY_THRESHOLD = 2

export function anomalies(regionSeries, minPostings) {
  const rows = []
  for (const region of regionSeries) {
    if ((region.total || 0) < minPostings) {
      continue
    }
    const points = region.shares.map((y, x) => ({ x, y }))
    const fit = linearFit(points)
    const residuals = points.map((p) => p.y - (fit.slope * p.x + fit.intercept))
    const mean = residuals.reduce((a, b) => a + b, 0) / (residuals.length || 1)
    const variance = residuals.reduce(
      (a, r) => a + (r - mean) * (r - mean), 0) / (residuals.length || 1)
    const sd = Math.sqrt(variance)
    // Against the size of the series, not against zero. A region that sits
    // exactly on its own line leaves residuals of about 1e-18 -- floating
    // point, not signal -- and dividing by that standard deviation turns
    // rounding error into a stack of five sigma anomalies. The scale is the
    // region's mean share, so the test is "did it move, relative to how big
    // it is" rather than "is this float exactly zero".
    const scale = region.shares.reduce((a, b) => a + b, 0)
      / (region.shares.length || 1)
    const moved = sd > Math.max(scale, 1) * 1e-9
    rows.push({
      region: region.region,
      total: region.total,
      // Zero rather than Infinity when a region never moves: a flat series
      // has no anomalies, and dividing by a standard deviation of zero would
      // mark every month as one.
      z: residuals.map((r) => (moved ? (r - mean) / sd : 0))
    })
  }
  return rows
}

/** The months that stand out, strongest first, for the summary line. */
export function notableAnomalies(rows, months, threshold = ANOMALY_THRESHOLD) {
  const out = []
  rows.forEach((row) => {
    row.z.forEach((z, i) => {
      if (Math.abs(z) >= threshold && months[i]) {
        out.push({ region: row.region, month: months[i], z })
      }
    })
  })
  return out.sort((a, b) => Math.abs(b.z) - Math.abs(a.z))
}
