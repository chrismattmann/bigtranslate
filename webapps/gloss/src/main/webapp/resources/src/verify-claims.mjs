// Do the hindsight panel's written claims still match what the index says?
//
// The panel pairs a sentence somebody wrote with a number measured live.
// That is the point of it, and it means a change to how sectors are matched
// can leave the sentence and the number disagreeing -- with the sentence
// winning, because it is the thing in large type.
//
// Imports the real SECTORS and the real arithmetic rather than restating
// them, so this cannot quietly measure something the page does not.
//
//   node src/verify-claims.mjs [solr-url]
import {
  SECTORS, SECTOR_FIELDS, sectorQuery, shareSeries, growthRate, wholeMonths
} from './analytics.js'
import { CHECKS } from './hindsight.js'

const SOLR = process.argv[2]
  || 'http://localhost:8985/solr/bigtranslate/select'

async function ask (facet, fq) {
  const q = new URLSearchParams({ q: '*:*', rows: '0', wt: 'json' })
  if (fq) q.append('fq', fq)
  q.set('json.facet', JSON.stringify(facet))
  const r = await fetch(`${SOLR}?${q.toString()}`)
  if (!r.ok) throw new Error(`solr ${r.status}`)
  return r.json()
}

const probe = await ask({ n: { type: 'query', q: `${SECTOR_FIELDS.precise}:[* TO *]` } })
const field = probe.facets.n.count > 0 ? SECTOR_FIELDS.precise : SECTOR_FIELDS.broad
console.log(`  sector field: ${field}\n`)

const facet = {
  months: {
    type: 'range', field: 'postedDate',
    start: '2012-07-01T00:00:00Z', end: '2013-12-28T00:00:00Z',
    gap: '+1MONTH', mincount: 1,
    facet: Object.fromEntries(SECTORS.map((s) =>
      [s.key, { type: 'query', q: sectorQuery(s, field) }]))
  }
}
const res = await ask(facet)
const months = wholeMonths(res.facets.months.buckets)
console.log(`  ${months.length} whole months of ${res.facets.months.buckets.length}\n`)

const rows = SECTORS.map((s) => {
  const series = shareSeries(months, s.key)
  const mean = series.reduce((a, b) => a + b, 0) / (series.length || 1)
  return { key: s.key, label: s.label, rate: growthRate(series), mean }
}).sort((a, b) => b.rate - a.rate)

console.log('  sector share trend, fastest rising first')
console.log(`  ${'sector'.padEnd(24)}${'per month'.padStart(11)}${'mean share'.padStart(12)}`)
for (const r of rows) {
  console.log(`  ${r.label.padEnd(24)}${(r.rate * 100).toFixed(2).padStart(10)}%`
    + `${(r.mean * 100).toFixed(2).padStart(11)}%`)
}

const claim = CHECKS.find((c) => c.key === 'construction')
console.log()
console.log(`  CLAIM: ${claim.claim}`)
console.log(`  measured fastest riser: ${rows[0].label}`)
const holds = rows[0].key === 'construction'
console.log(`  => ${holds ? 'HOLDS' : 'CONTRADICTED — the panel would print a claim '
  + 'its own live number disagrees with'}`)
process.exit(holds ? 0 : 2)
