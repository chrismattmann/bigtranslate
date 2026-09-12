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
// The arithmetic behind the Analytics tab.
//
// Kept apart from the panels that draw it for the same reason progress.js
// is: a projected line and a shaded cell are assertions about the data, and
// the assertion is the part worth being sure of. Everything here is a pure
// function of numbers that came back from Solr.
//
// The questions come from the XDATA employment dataset's own challenge list.
// Which of them this can answer is a property of the index, not of the
// drawing, so the panels name their question and say what they are built on.

/**
 * Sectors, as sets of words that appear in a job title.
 *
 * The corpus has 1,012,292 distinct titles and no taxonomy, so a sector has
 * to be inferred. Words rather than exact titles because the titles are a
 * long tail: the top 500 of them are 19% of the postings, so classifying by
 * whole title answers the question for a fifth of the corpus.
 *
 * These are English because the pipeline has already translated the titles.
 * That is the point of the translation and it is what makes this list short
 * enough to read: the Spanish would need every inflection of every word.
 */
export const SECTORS = [
  { key: 'office', label: 'Office and admin',
    words: ['Assistant', 'Secretary', 'Administrative', 'Accountant',
            'Analyst', 'Receptionist', 'Clerk', 'Auxiliary'] },
  { key: 'retail', label: 'Retail and sales',
    words: ['Sales', 'Seller', 'Vendor', 'Cashier', 'Commercial', 'Store',
            'Shop', 'Promoter'] },
  { key: 'industrial', label: 'Industry and trades',
    words: ['Operator', 'Mechanic', 'Welder', 'Production', 'Maintenance',
            'Electrician', 'Machinist'] },
  { key: 'it', label: 'Software and IT',
    words: ['Developer', 'Programmer', 'Software', 'Systems', 'Web',
            'Database'] },
  { key: 'medical', label: 'Health',
    words: ['Nurse', 'Doctor', 'Medical', 'Dentist', 'Pharmacy', 'Nursing',
            'Therapist'] },
  { key: 'transport', label: 'Transport and logistics',
    words: ['Driver', 'Logistics', 'Delivery', 'Courier', 'Warehouse',
            'Transport'] },
  { key: 'teaching', label: 'Education',
    words: ['Teacher', 'Professor', 'Instructor', 'Tutor', 'Trainer'] },
  { key: 'hospitality', label: 'Food and hospitality',
    words: ['Waiter', 'Chef', 'Cook', 'Kitchen', 'Bartender', 'Hotel'] },
  { key: 'construction', label: 'Construction',
    words: ['Construction', 'Builder', 'Architect', 'Plumber', 'Mason',
            'Painter'] }
]

/**
 * Which field the sector words are matched against.
 *
 * title_txt is a tokenised copy of the title and is what the question is
 * about. It arrives with the next re-index; until then the catch-all text
 * field is the only tokenised thing in the schema, and it is a copy of every
 * field, so a match there may have come from a company name or a salary
 * note rather than the title.
 *
 * The panels say which was used, because "42.9% of postings are in a sector"
 * means something different for each.
 */
export const SECTOR_FIELDS = { precise: 'title_txt', broad: 'text' }

/** The Solr query for one sector against a given field. */
export function sectorQuery(sector, field) {
  return `${field}:(${sector.words.join(' OR ')})`
}

/**
 * A json.facet body asking for every sector at once.
 *
 * One request rather than nine: the nine together take about the same time
 * as any one of them, and a panel that issues nine requests renders nine
 * times, each with a different subset of its own bars.
 */
export function sectorFacet(field, extra) {
  const facet = {}
  SECTORS.forEach((s) => {
    facet[s.key] = { type: 'query', q: sectorQuery(s, field) }
  })
  return Object.assign(facet, extra || {})
}

/** Counts out of a json.facet response, as a flat {key: count}. */
export function sectorCounts(bucket) {
  const out = {}
  SECTORS.forEach((s) => {
    const node = bucket ? bucket[s.key] : null
    out[s.key] = node && typeof node.count === 'number' ? node.count : 0
  })
  return out
}

/** Shares of the sector total, so places of different sizes compare. */
export function sectorShares(counts) {
  const total = SECTORS.reduce((sum, s) => sum + (counts[s.key] || 0), 0)
  const out = {}
  SECTORS.forEach((s) => {
    out[s.key] = total > 0 ? (counts[s.key] || 0) / total : 0
  })
  out.total = total
  return out
}

/**
 * Q14: what kind of place this is, from what it advertises for.
 *
 * The zone is the sector with the largest share, and how sure that is comes
 * from how far ahead of the next one it is. A city whose top two sectors are
 * 21% and 20% has not been classified by being called "office"; the margin
 * is what says so, and the panel shows it rather than only the label.
 */
export function zone(counts) {
  const shares = sectorShares(counts)
  const ranked = SECTORS
    .map((s) => ({ key: s.key, label: s.label, share: shares[s.key] }))
    .sort((a, b) => b.share - a.share)
  const top = ranked[0]
  const next = ranked[1]
  if (!top || top.share === 0) {
    return { key: null, label: 'No sector postings', share: 0, margin: 0, ranked }
  }
  return {
    key: top.key,
    label: top.label,
    share: top.share,
    margin: top.share - (next ? next.share : 0),
    ranked
  }
}

/**
 * Least squares fit of y against x.
 *
 * Returns the line and the R squared, because a straight line can be drawn
 * through anything and the fit is how much it is worth. Panels that project
 * show it.
 */
export function linearFit(points) {
  const n = points.length
  if (n < 2) {
    return { slope: 0, intercept: n === 1 ? points[0].y : 0, r2: 0, n }
  }
  let sx = 0
  let sy = 0
  for (const p of points) {
    sx += p.x
    sy += p.y
  }
  const mx = sx / n
  const my = sy / n
  let sxy = 0
  let sxx = 0
  for (const p of points) {
    sxy += (p.x - mx) * (p.y - my)
    sxx += (p.x - mx) * (p.x - mx)
  }
  const slope = sxx === 0 ? 0 : sxy / sxx
  const intercept = my - slope * mx
  let ssRes = 0
  let ssTot = 0
  for (const p of points) {
    const fitted = slope * p.x + intercept
    ssRes += (p.y - fitted) * (p.y - fitted)
    ssTot += (p.y - my) * (p.y - my)
  }
  const r2 = ssTot === 0 ? 0 : 1 - ssRes / ssTot
  return { slope, intercept, r2, n }
}

/**
 * Q1: where a series goes next if it keeps doing what it has been doing.
 *
 * This is a straight line through eighteen monthly points and nothing more.
 * It has no seasonality, no saturation and no notion that a job market can
 * turn, and the corpus itself ends mid-collection: the last month is a
 * partial one because the scrape stopped, not because hiring did. Presented
 * as a projection rather than a forecast, drawn dashed, and carrying its own
 * R squared so a bad fit looks like one.
 */
export function project(series, ahead) {
  const points = series.map((v, i) => ({ x: i, y: v }))
  const fit = linearFit(points)
  const out = []
  for (let i = 0; i < (ahead || 0); i++) {
    const x = series.length + i
    out.push(Math.max(0, fit.slope * x + fit.intercept))
  }
  return { fit, projected: out }
}

/**
 * A sector's share of each month, rather than its count.
 *
 * The count is the wrong quantity and it is wrong in a way that looks like
 * an answer. Collection wound down over this corpus: postings per month fall
 * at about 7% a month across the whole of it, so every sector's raw count
 * falls too, and every sector reads as declining. Measured that way all nine
 * had negative growth, which is the scraper stopping rather than the job
 * market doing anything, and it left the openings panel with nothing to draw
 * and no way to say why.
 *
 * A share is what the month's postings were about, whatever number of them
 * were collected, and it is comparable between months and between sectors.
 */
export function shareSeries(buckets, key) {
  return (buckets || []).map((b) => {
    const total = b && typeof b.count === 'number' ? b.count : 0
    const hit = b && b[key] && typeof b[key].count === 'number'
      ? b[key].count : 0
    return total > 0 ? hit / total : 0
  })
}

/**
 * Growth as the fitted slope over the mean, so sectors of different sizes
 * compare. A sector averaging a thousand postings a month and gaining fifty
 * is growing as fast as one averaging a hundred thousand and gaining five
 * thousand, and the second is the one a raw slope would pick.
 */
export function growthRate(series) {
  if (!series.length) {
    return 0
  }
  const mean = series.reduce((a, b) => a + b, 0) / series.length
  if (mean === 0) {
    return 0
  }
  return linearFit(series.map((v, i) => ({ x: i, y: v }))).slope / mean
}

/**
 * Q5: where a sector that is growing is not yet being hired for.
 *
 * Two things have to be true at once. The sector has to be growing across
 * the corpus, or there is no reason to think it will arrive anywhere; and it
 * has to be thinner in this region than it is everywhere else, or it has
 * already arrived. The score is the product, so a sector that is booming
 * nationally and already saturated locally scores zero, and so does one that
 * is absent locally and going nowhere.
 *
 * A gap is only scored when the region has enough postings to mean anything.
 * Below that, one region's twelve postings produce a shortfall of 100% in
 * every sector and lead the table.
 */
export const MIN_REGION_POSTINGS = 5000

export function opportunities(regions, nationalShares, nationalGrowth) {
  const out = []
  regions.forEach((region) => {
    if ((region.total || 0) < MIN_REGION_POSTINGS) {
      return
    }
    const shares = sectorShares(region.counts)
    SECTORS.forEach((s) => {
      const national = nationalShares[s.key] || 0
      const local = shares[s.key] || 0
      const growth = nationalGrowth[s.key] || 0
      const gap = national - local
      if (gap <= 0 || growth <= 0) {
        return
      }
      out.push({
        region: region.name,
        sector: s.key,
        label: s.label,
        local,
        national,
        gap,
        growth,
        score: gap * growth
      })
    })
  })
  return out.sort((a, b) => b.score - a.score)
}

/** A month bucket's label, from the ISO instant Solr returns. */
export function monthLabel(iso) {
  if (typeof iso !== 'string' || iso.length < 7) {
    return ''
  }
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const month = Number(iso.slice(5, 7))
  if (!(month >= 1 && month <= 12)) {
    return iso.slice(0, 7)
  }
  return `${months[month - 1]} ${iso.slice(2, 4)}`
}

/**
 * Months whose counts are a whole month of collection.
 *
 * The first and last buckets of this corpus are partial: collection starts
 * on 2012-07-31 and stops on 2013-12-13, so July 2012 holds one day and
 * December 2013 holds thirteen. Left in, a trend line reads the end of the
 * scrape as a collapse in hiring, which is the most confident wrong thing
 * this tab could say.
 */
export function wholeMonths(buckets) {
  if (!buckets || buckets.length < 3) {
    return buckets || []
  }
  const counts = buckets.map((b) => b.count || 0)
  const middle = counts.slice(1, -1).sort((a, b) => a - b)
  const median = middle[Math.floor(middle.length / 2)] || 0
  const floor = median * 0.35
  let first = 0
  let last = buckets.length - 1
  if (counts[first] < floor) {
    first += 1
  }
  if (counts[last] < floor) {
    last -= 1
  }
  return buckets.slice(first, last + 1)
}
