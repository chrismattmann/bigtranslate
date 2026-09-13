<template>
  <section class="challenges" ref="root">

    <div v-if="tip" class="tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      <strong>{{ tip.title }}</strong>
      <span v-for="(line, i) in tip.lines" :key="i">{{ line }}</span>
    </div>

    <article v-if="error" class="card banner">{{ error }}</article>
    <article v-else-if="loading" class="card">
      <p class="loading">Asking Solr…</p>
    </article>
    <p v-else-if="failed.length" class="caveat partial">
      Solr did not answer for {{ failed.join(', ') }}, so
      {{ failed.length === 1 ? 'that panel is' : 'those panels are' }} empty
      below. The rest of the page is unaffected — each question is asked on
      its own.
    </p>

    <template v-else>
      <!-- A15, V3 -->
      <article class="card">
        <h3>Who does the hiring, and where</h3>
        <p class="q">Challenges 15 and V3 · corporate presence · are there territories?</p>
        <svg ref="firmsSvg" class="chart"></svg>
        <p class="note">
          The <strong>{{ firms.length }}</strong> largest employers by
          postings, each bar split by country. There are
          <strong>{{ companyCount }}</strong> distinct company names in the
          corpus and the largest holds
          <strong>{{ (hhi.top * 100).toFixed(2) }}%</strong> of it, so this is
          a market with a very long tail rather than a handful of giants.
          <strong>HHI {{ Math.round(hhi.hhi) }}</strong> over the names shown,
          against the 1,500 below which competition authorities call a market
          unconcentrated — measured on
          {{ (hhi.covered * 100).toFixed(1) }}% of postings, so read it as a
          floor.
        </p>
        <p class="note">
          <strong>Territory</strong> is the share of a company's own postings
          sitting in its single largest region: 1 is one region only.
          {{ territorial }}
        </p>
        <p class="note">
          Bars are split by country, and the grey segment is the
          <strong>{{ 100 - Number(countryShare.replace('%', '')) }}%</strong>
          of postings the geo-fixing never reached — the corpus records the
          country only inside the location text. Territory is computed over
          regions, which every posting has.
        </p>
      </article>

      <!-- V2 -->
      <article class="card">
        <h3>Whether the big agencies were growing</h3>
        <p class="q">Challenge V2 · how companies change over time</p>
        <svg ref="firmTrendSvg" class="chart"></svg>
        <p class="note">
          Each company's <strong>share of its month</strong>, not its count.
          Counts fall everywhere — the scrape wound down about 7% a month —
          so on raw numbers every company on the board is dying. Share asks
          the different question of who was gaining on whom. Dashed lines are
          least squares fits with their R² printed; a fit through eighteen
          points is a description, not a forecast.
        </p>
      </article>

      <!-- A8 -->
      <article class="card">
        <h3>What the stated salaries did</h3>
        <p class="q">Challenge 8 · how compensation changes over time and by locale</p>
        <p v-if="!salarySeries.length" class="caveat">
          No numeric salaries in the index yet. <code>salary_d</code> is
          written by the join, so this panel fills in after the next index
          run. Everything else on this page works without it.
        </p>
        <template v-else>
          <svg ref="salarySvg" class="chart"></svg>
          <p class="note">
            Each country <strong>indexed to 100 at its own first month</strong>.
            Levels cannot be compared across these currencies — a Colombian
            peso and a Peruvian sol are three orders of magnitude apart — so a
            chart of raw medians would be a chart of which country posted most
            that month. Indexed, each country is compared only against itself,
            which is what the question asks.
          </p>
          <p class="note">
            Medians, not means, over the
            <strong>{{ salaryShare }}</strong> of postings that state a figure
            at all. The rest say <em>To be agreed</em> — 15,276,117 of them —
            or <em>In an interview</em> or <em>Negotiable</em>. Months with fewer than
            {{ minSalary }} stated salaries are dropped rather than drawn.
          </p>
          <p class="note">
            And only where the country is known, which is
            <strong>{{ countryShare }}</strong> of postings: the corpus
            records it inside the location text, and the records without one
            are the records the geo-fixing never reached. So this is a chart
            over the intersection of two partial columns, not over the corpus.
          </p>
        </template>
      </article>

      <!-- A7 -->
      <article class="card">
        <h3>Which regions were losing ground</h3>
        <p class="q">Challenge 7 · areas of economic downtrend</p>
        <svg ref="downSvg" class="chart"></svg>
        <p class="note">
          Change in each region's <strong>share of the month</strong>, as a
          percentage of its own average share, so a small region losing a
          tenth of itself ranks alongside a large one doing the same. On raw
          counts every region falls, because the collection was winding down;
          that would be a chart of the scraper. Regions under
          {{ minRegion }} postings are left out.
        </p>
      </article>

      <!-- A11 -->
      <article class="card">
        <h3>What level of job was being advertised</h3>
        <p class="q">Challenge 11 · academic skill level by country</p>
        <svg ref="skillSvg" class="chart"></svg>
        <p class="note">
          The corpus has <strong>no education column</strong>. This reads the
          job title, which the pipeline translated into English, and sorts it
          into four tiers by the words in it. It is an inference: a
          <em>Manager</em> in a corner shop and a <em>Manager</em> in a bank
          are one tier here, and a title matching two tiers — <em>Assistant
          Manager</em> — counts in both, so these are shares of the matched
          titles rather than of all postings.
        </p>
      </article>

      <!-- A10 -->
      <article class="card">
        <h3>How long a posting lasts, by region</h3>
        <p class="q">Challenge 10 · how quickly jobs are filled, by region</p>
        <svg ref="fillSvg" class="chart"></svg>
        <p class="note">
          Mean days between first and last seen, <strong>one row per
          job</strong> rather than per posting-day: averaged over rows the
          answer is {{ lifeOverRows }} days, because every posting is weighted
          by its own length. Collapsed it is {{ lifeCollapsed }}.
        </p>
        <p class="note">
          A posting coming down is <strong>not</strong> evidence it was
          filled. The corpus has an <code>applications</code> column and it
          holds <em>how</em> to apply — “Send CV by email” — not how many did.
          Lifetime is the only proxy available and it is a weak one.
        </p>
      </article>

      <!-- A13 -->
      <article class="card">
        <h3>Transport and logistics</h3>
        <p class="q">Challenge 13 · what the data says about transport services</p>
        <svg ref="transportSvg" class="chart"></svg>
        <p class="note">
          Transport and logistics as a share of each country's postings, over
          the collection. The sector is matched on
          <code>{{ sectorField }}</code> by the same word list the panels
          above use — driver, logistics, transport, courier, warehouse and
          the rest.
        </p>
      </article>

      <!-- V4 -->
      <article class="card">
        <h3>Whether any of it is seasonal</h3>
        <p class="q">Challenge V4 · seasonal trends by job category</p>
        <svg ref="seasonSvg" class="chart"></svg>
        <p class="note">
          One line per calendar year, deliberately. The corpus covers
          <strong>eighteen months</strong> — one cycle and half of another —
          so folding it into a single seasonal curve would average August 2012
          with August 2013 and present two observations as a season. Drawn
          this way the reader can see the two lines agree or not, and can see
          that one of them stops in December.
        </p>
      </article>

      <!-- A3 -->
      <article class="card">
        <h3>Months that did not fit the trend</h3>
        <p class="q">Challenge 3 · temporal and geospatial anomalies</p>
        <svg ref="anomalySvg" class="chart"></svg>
        <p class="note">
          Each region's share of the month against <strong>its own least
          squares line</strong>, as a residual in standard deviations. Against
          its own trend rather than against the other regions, because the
          whole corpus declines and a shared decline is not an anomaly. Blue
          is above the line, red below; anything past ±{{ threshold }} is
          called out.
        </p>
        <p class="note">{{ anomalyLine }}</p>
      </article>

    </template>
  </section>
</template>

<script>
// The second half of the challenge questions.
//
// A separate component from AnalyticsPanel on purpose: that one is already
// nine hundred lines and answers a coherent set of questions about sectors
// and regions. These answer a different set, off different fields, and
// bolting them on would have made one file nobody can hold in their head.
//
// The arithmetic is in challenges.js and tested there. What is here is the
// asking and the drawing.
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as d3 from 'd3'
import { solrFacet } from '../api.js'
import {
  SECTORS, SECTOR_FIELDS, sectorQuery, monthLabel, wholeMonths,
  MIN_REGION_POSTINGS
} from '../analytics.js'
import {
  concentration, territory, salaryIndex, salaryTrend, trendByRegion,
  SKILL_TIERS, skillFacet, skillMix, byCalendarMonth, anomalies,
  notableAnomalies, ANOMALY_THRESHOLD, MIN_SALARY_RECORDS, MONTH_NAMES
} from '../challenges.js'

const FIRM_LIMIT = 12
const FIRM_TREND_LIMIT = 6
const COUNTRY_LIMIT = 6
const REGION_LIMIT = 14
// The nested facets go deeper than the lists they feed. A terms facet inside
// a month bucket returns that month's top N, which is not the same set as the
// corpus-wide top N: a region that is fourteenth overall can be twentieth in
// a quiet month, come back absent, and be read as a month of zero postings.
// On the downtrend and anomaly panels that is a fabricated collapse. Deep
// enough that the regions being plotted are present in every month.
const NESTED_REGION_LIMIT = 60
const NESTED_COUNTRY_LIMIT = 20
const TRANSPORT = 'transport'
// Nearly half the corpus was never geo-fixed and so carries no country. It
// is a segment on the bar rather than a missing piece of one.
const UNKNOWN_COUNTRY = 'not geo-fixed'

export default {
  name: 'ChallengePanels',
  setup() {
    const root = ref(null)
    const firmsSvg = ref(null)
    const firmTrendSvg = ref(null)
    const salarySvg = ref(null)
    const downSvg = ref(null)
    const skillSvg = ref(null)
    const fillSvg = ref(null)
    const transportSvg = ref(null)
    const seasonSvg = ref(null)
    const anomalySvg = ref(null)

    const loading = ref(true)
    const error = ref('')
    const tip = ref(null)
    const sectorField = ref(SECTOR_FIELDS.broad)
    const firms = ref([])
    const companyCount = ref('')
    const hhi = ref({ hhi: 0, covered: 0, top: 0 })
    const territorial = ref('')
    const salarySeries = ref([])
    const salaryShare = ref('')
    const lifeOverRows = ref('')
    const lifeCollapsed = ref('')
    const anomalyLine = ref('')
    const failed = ref([])
    const countryShare = ref('')
    const minRegion = MIN_REGION_POSTINGS.toLocaleString()
    const minSalary = MIN_SALARY_RECORDS.toLocaleString()
    const threshold = ANOMALY_THRESHOLD

    let observer = null
    let data = null
    let drawnAt = 0

    const firmColour = d3.scaleOrdinal(d3.schemeTableau10)
    const countryColour = d3.scaleOrdinal(d3.schemeSet2)
    const tierColour = d3.scaleOrdinal()
      .domain(SKILL_TIERS.map((t) => t.key))
      .range(['#bab0ac', '#4e79a7', '#59a14f', '#e1a03c'])

    function frame(node, height) {
      const width = Math.max(360, (node.parentNode || {}).clientWidth || 720)
      const sel = d3.select(node)
      sel.selectAll('*').remove()
      sel.attr('viewBox', `0 0 ${width} ${height}`)
        .attr('width', '100%').attr('height', height)
      return { sel, width, height }
    }

    function hoverable(sel, describe) {
      sel.style('cursor', 'crosshair')
        .on('mousemove', (event, d) => {
          const info = describe(d)
          if (!info || !root.value) {
            return
          }
          const box = root.value.getBoundingClientRect()
          tip.value = {
            x: event.clientX - box.left + 14,
            y: event.clientY - box.top + 14,
            title: info.title,
            lines: info.lines || []
          }
        })
        .on('mouseleave', () => { tip.value = null })
    }

    function legend(sel, x, y, items) {
      const g = sel.append('g').attr('transform', `translate(${x},${y})`)
      items.forEach((item, i) => {
        const row = g.append('g').attr('transform', `translate(0,${i * 17})`)
        row.append('rect').attr('width', 11).attr('height', 11).attr('rx', 2)
          .attr('fill', item.colour)
        row.append('text').attr('x', 16).attr('y', 10)
          .attr('class', 'leg').text(item.label)
      })
      return g
    }

    /** Whether the tokenised title copy has been indexed yet. */
    async function pickSectorField() {
      try {
        const probe = await solrFacet(
          { n: { type: 'query', q: `${SECTOR_FIELDS.precise}:[* TO *]` } })
        const n = probe.facets && probe.facets.n ? probe.facets.n.count : 0
        sectorField.value = n > 0 ? SECTOR_FIELDS.precise : SECTOR_FIELDS.broad
      } catch (e) {
        sectorField.value = SECTOR_FIELDS.broad
      }
    }

    /**
     * One question, and a note rather than a blank page when it fails.
     *
     * load() used to be a single try/catch around every query. Any one of
     * them failing -- a slow facet over 119 million documents, a field not
     * indexed yet -- took all nine panels with it and left the reader a
     * sentence about an exception. The panels do not depend on each other,
     * so a failure should cost one of them.
     */
    async function attempt(what, run, fallback) {
      try {
        return await run()
      } catch (e) {
        failed.value = failed.value.concat(what)
        return fallback
      }
    }

    /** Region and country series, from one month-by-month answer. */
    function series(buckets, key, names) {
      return names.map((name) => {
        const shares = []
        let total = 0
        let missing = 0
        buckets.forEach((b) => {
          const found = ((b[key] || {}).buckets || [])
            .find((x) => x.val === name)
          if (!found) {
            missing += 1
          }
          const count = found ? found.count : 0
          total += count
          shares.push(b.count ? count / b.count : 0)
        })
        // A name absent from a month's nested facet is a name that fell below
        // the nested limit, not a month with no postings. Reading it as zero
        // is a collapse that never happened, so a series with holes in it is
        // dropped rather than plotted.
        return { region: name, total, shares, missing }
      }).filter((row) => row.missing === 0)
    }

    async function load() {
      loading.value = true
      error.value = ''
      try {
        await pickSectorField()
        const field = sectorField.value

        // One pass over the months carries four panels: downtrend,
        // anomalies, transport and seasonality. Eighteen range buckets is
        // cheap; asking four times over 119 million documents is not.
        const overall = await attempt('the corpus overview', () => solrFacet({
          months: {
            type: 'range',
            field: 'postedDate',
            start: '2012-07-01T00:00:00Z',
            end: '2013-12-28T00:00:00Z',
            gap: '+1MONTH',
            mincount: 1,
            facet: {
              region: { type: 'terms', field: 'department',
                        limit: NESTED_REGION_LIMIT },
              country: { type: 'terms', field: 'country',
                         limit: NESTED_COUNTRY_LIMIT },
              transport: {
                type: 'query',
                q: sectorQuery(SECTORS.find((s) => s.key === TRANSPORT), field)
              }
            }
          },
          regions: { type: 'terms', field: 'department', limit: REGION_LIMIT },
          countries: { type: 'terms', field: 'country', limit: COUNTRY_LIMIT },
          companies: { type: 'terms', field: 'company', limit: FIRM_LIMIT,
                       facet: { country: { type: 'terms', field: 'country',
                                           limit: COUNTRY_LIMIT } } },
          distinctCompanies: 'unique(company)',
          // Not every posting has one. The panels that group by country
          // have to say how much of the corpus they are answering over.
          withCountry: { type: 'query', q: 'country:[* TO *]' }
        }), { facets: {}, response: { numFound: 0 } })
        const f = overall.facets || {}
        const months = wholeMonths((f.months || {}).buckets || [])
        const regionNames = ((f.regions || {}).buckets || []).map((b) => b.val)
        const countryNames = ((f.countries || {}).buckets || []).map((b) => b.val)
        const companies = ((f.companies || {}).buckets || [])
        const corpus = overall.response ? overall.response.numFound : 0

        const located = ((f.withCountry || {}).count) || 0
        countryShare.value = corpus
          ? `${((located / corpus) * 100).toFixed(0)}%`
          : '0%'
        companyCount.value = Number(f.distinctCompanies || 0).toLocaleString()
        hhi.value = concentration(companies, corpus)
        firms.value = companies

        const worst = companies
          .map((c) => ({
            name: c.val,
            t: territory(((c.country || {}).buckets || []))
          }))
          .filter((x) => x.t.total > 0)
          .sort((a, b) => b.t.share - a.t.share)[0]
        territorial.value = worst
          ? `The most concentrated of them is ${worst.name}, with `
            + `${(worst.t.share * 100).toFixed(0)}% of its postings in `
            + `${worst.t.region} alone.`
          : ''

        // The big names, month by month, as a share of the month.
        const named = companies.slice(0, FIRM_TREND_LIMIT)
        const firmTrend = await attempt('employers over time', () => solrFacet({
          months: {
            type: 'range',
            field: 'postedDate',
            start: '2012-07-01T00:00:00Z',
            end: '2013-12-28T00:00:00Z',
            gap: '+1MONTH',
            mincount: 1,
            facet: named.reduce((acc, c, i) => {
              acc['c' + i] = {
                type: 'query',
                q: `company:"${String(c.val).replace(/"/g, '')}"`
              }
              return acc
            }, {})
          }
        }), { facets: {} })

        // Salaries. fq rather than a filter inside the facet, so a bucket's
        // count is the number of postings that state a figure -- which is
        // the number the panel has to be able to show and drop on.
        let salary = { facets: {} }
        let stated = 0
        try {
          const probe = await solrFacet({ n: { type: 'query', q: 'salary_d:[* TO *]' } })
          stated = ((probe.facets || {}).n || {}).count || 0
          if (stated > 0) {
            salary = await solrFacet({
              country: {
                type: 'terms', field: 'country', limit: COUNTRY_LIMIT,
                facet: {
                  months: {
                    type: 'range', field: 'postedDate',
                    start: '2012-07-01T00:00:00Z',
                    end: '2013-12-28T00:00:00Z',
                    gap: '+1MONTH', mincount: 1,
                    facet: { median: 'percentile(salary_d,50)' }
                  }
                }
              }
            }, { fq: 'salary_d:[* TO *]' })
          }
        } catch (e) {
          stated = 0
        }
        salaryShare.value = corpus
          ? `${((stated / corpus) * 100).toFixed(1)}%`
          : '0%'

        const skills = await attempt('skill levels', () => solrFacet({
          country: {
            type: 'terms', field: 'country', limit: COUNTRY_LIMIT,
            facet: skillFacet(field)
          }
        }), { facets: {} })

        // One row per job rather than per posting-day. Collapsing is what
        // makes the answer about postings instead of about how long each one
        // happened to stay up.
        const lives = await attempt('posting lifetimes', () => solrFacet({
          all: 'avg(div(ms(lastSeenDate,firstSeenDate),86400000))',
          region: {
            type: 'terms', field: 'department', limit: REGION_LIMIT,
            facet: { days: 'avg(div(ms(lastSeenDate,firstSeenDate),86400000))' }
          }
        }, { fq: '{!collapse field=url}' }), { facets: {} })
        const rows = await attempt('lifetime over rows', () => solrFacet(
          { all: 'avg(div(ms(lastSeenDate,firstSeenDate),86400000))' }),
        { facets: {} })

        lifeOverRows.value =
          ((rows.facets || {}).all || 0).toFixed(1)
        lifeCollapsed.value =
          `${(((lives.facets || {}).all) || 0).toFixed(1)} days`

        data = {
          months,
          regionSeries: series(months, 'region', regionNames),
          countrySeries: series(months, 'country', countryNames),
          countryNames,
          companies,
          named,
          firmMonths: ((firmTrend.facets || {}).months || {}).buckets || [],
          salary: (salary.facets || {}).country || { buckets: [] },
          skills: (skills.facets || {}).country || { buckets: [] },
          lives: ((lives.facets || {}).region || {}).buckets || []
        }

        const rowsZ = anomalies(data.regionSeries, MIN_REGION_POSTINGS)
        const labels = months.map((b) => monthLabel(b.val))
        const notable = notableAnomalies(rowsZ, labels)
        anomalyLine.value = notable.length
          ? `${notable.length} month${notable.length === 1 ? '' : 's'} past `
            + `±${ANOMALY_THRESHOLD}. The strongest is ${notable[0].region} in `
            + `${notable[0].month}, ${notable[0].z > 0 ? '+' : ''}`
            + `${notable[0].z.toFixed(1)} standard deviations from its own line.`
          : `Nothing past ±${ANOMALY_THRESHOLD}. Every region tracked its own `
            + 'trend across the collection.'
        data.anomalyRows = rowsZ
        data.anomalyLabels = labels

        // The salary panel needs its series before the template decides
        // whether to render an svg for it to draw into.
        const built = []
        ;(data.salary.buckets || []).forEach((b) => {
          const monthly = ((b.months || {}).buckets || []).map((m) => ({
            val: m.val, median: m.median || 0, n: m.count || 0
          }))
          const indexed = salaryIndex(monthly)
          if (indexed.length >= 3) {
            built.push({
              country: b.val,
              points: indexed,
              trend: salaryTrend(indexed)
            })
          }
        })
        salarySeries.value = built

        loading.value = false
        await nextTick()
        redraw()
      } catch (e) {
        error.value = `Analytics could not be built: ${e.message || e}`
        loading.value = false
      }
    }

    function redraw() {
      if (!data || error.value) {
        return
      }
      drawnAt = root.value ? Math.round(root.value.clientWidth) : 0
      drawFirms()
      drawFirmTrend()
      drawSalary()
      drawDowntrend()
      drawSkills()
      drawFill()
      drawTransport()
      drawSeason()
      drawAnomalies()
    }

    /** Stacked horizontal bars: who hires, split by where. */
    function drawFirms() {
      if (!firmsSvg.value || !data.companies.length) {
        return
      }
      const rows = data.companies
      const left = 190
      const right = 150
      const top = 14
      const barH = 22
      const { sel, width } = frame(
        firmsSvg.value, top + rows.length * barH + 30)
      const max = d3.max(rows, (r) => r.count) || 1
      const x = d3.scaleLinear().domain([0, max])
        .range([left, Math.max(left + 40, width - right)])

      const countries = Array.from(new Set(rows.flatMap(
        (r) => ((r.country || {}).buckets || []).map((b) => b.val)))).slice(0, 8)
      countryColour.domain(countries)

      rows.forEach((row, i) => {
        const y = top + i * barH
        sel.append('text').attr('x', left - 10).attr('y', y + 15)
          .attr('text-anchor', 'end').attr('class', 'lbl')
          .text(String(row.val).length > 26
            ? String(row.val).slice(0, 25) + '…' : row.val)
        let cursor = left
        const known = ((row.country || {}).buckets || [])
        const t = territory(known)
        // The records with no country are the records the geo-fixing never
        // reached, and they are nearly half the corpus. Without a segment for
        // them the bar is shorter than the number printed at the end of it,
        // and the reader is left to wonder which is wrong.
        const accounted = known.reduce((a, b) => a + (b.count || 0), 0)
        const parts = accounted < row.count
          ? known.concat([{ val: UNKNOWN_COUNTRY, count: row.count - accounted }])
          : known
        parts.forEach((part) => {
          const w = x(part.count) - x(0)
          const rect = sel.append('rect')
            .attr('x', cursor).attr('y', y + 2)
            .attr('width', Math.max(0, w)).attr('height', barH - 7)
            .attr('fill', part.val === UNKNOWN_COUNTRY
              ? '#d7dde3' : countryColour(part.val))
          hoverable(rect, () => ({
            title: row.val,
            lines: [
              `${part.val}: ${part.count.toLocaleString()} postings`,
              `${(100 * part.count / row.count).toFixed(0)}% of this employer`
            ]
          }))
          cursor += w
        })
        sel.append('text').attr('x', cursor + 8).attr('y', y + 15)
          .attr('class', 'val')
          .text(`${(row.count / 1000).toFixed(0)}k · territory `
            + `${t.share.toFixed(2)}`)
      })
      legend(sel, left, top + rows.length * barH + 6,
        countries.slice(0, 4).map((c) => ({ label: c, colour: countryColour(c) }))
          .concat([{ label: UNKNOWN_COUNTRY, colour: '#d7dde3' }]))
    }

    /** Multi-line: each big employer's share of the month, with its fit. */
    function drawFirmTrend() {
      if (!firmTrendSvg.value || !data.firmMonths.length) {
        return
      }
      const buckets = wholeMonths(data.firmMonths)
      const height = 300
      const left = 54
      const right = 190
      const { sel, width } = frame(firmTrendSvg.value, height)
      const plotR = Math.max(left + 60, width - right)
      const x = d3.scalePoint().domain(buckets.map((b, i) => i))
        .range([left, plotR]).padding(0.5)
      const lines = data.named.map((c, ci) => ({
        name: c.val,
        points: buckets.map((b, i) => {
          const cell = b['c' + ci] || {}
          return { i, y: b.count ? (cell.count || 0) / b.count : 0 }
        })
      }))
      const max = d3.max(lines, (l) => d3.max(l.points, (p) => p.y)) || 0.01
      const y = d3.scaleLinear().domain([0, max * 1.1]).range([height - 34, 14])

      sel.append('g').attr('transform', `translate(${left},0)`)
        .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.2%')))
        .attr('class', 'axis')
      buckets.forEach((b, i) => {
        if (i % 3 === 0) {
          sel.append('text').attr('x', x(i)).attr('y', height - 16)
            .attr('text-anchor', 'middle').attr('class', 'tick')
            .text(monthLabel(b.val))
        }
      })

      const line = d3.line().x((p) => x(p.i)).y((p) => y(p.y))
      lines.forEach((l, li) => {
        sel.append('path').datum(l.points).attr('fill', 'none')
          .attr('stroke', firmColour(li)).attr('stroke-width', 2)
          .attr('d', line)
        l.points.forEach((p) => {
          const dot = sel.append('circle').attr('cx', x(p.i)).attr('cy', y(p.y))
            .attr('r', 3).attr('fill', firmColour(li))
          hoverable(dot, () => ({
            title: l.name,
            lines: [`${monthLabel(buckets[p.i].val)}: `
              + `${(p.y * 100).toFixed(2)}% of the month`]
          }))
        })
        const fit = salaryTrend(l.points.map((p) => ({ index: p.y })))
        if (fit.n >= 3) {
          const a = { i: 0, y: l.points[0].y }
          const b = { i: l.points.length - 1,
                      y: l.points[0].y + fit.perMonth * (l.points.length - 1) }
          sel.append('path').datum([a, b]).attr('fill', 'none')
            .attr('stroke', firmColour(li)).attr('stroke-width', 1)
            .attr('stroke-dasharray', '4 3').attr('opacity', 0.7)
            .attr('d', line)
        }
      })
      legend(sel, plotR + 16, 16, lines.map((l, li) => ({
        label: String(l.name).length > 22
          ? String(l.name).slice(0, 21) + '…' : l.name,
        colour: firmColour(li)
      })))
    }

    /** Multi-line: each country's stated salaries, indexed to its own start. */
    function drawSalary() {
      if (!salarySvg.value || !salarySeries.value.length) {
        return
      }
      const rows = salarySeries.value
      const height = 300
      const left = 54
      const right = 200
      const { sel, width } = frame(salarySvg.value, height)
      const plotR = Math.max(left + 60, width - right)
      const span = d3.max(rows, (r) => r.points.length) || 2
      const x = d3.scaleLinear().domain([0, span - 1]).range([left, plotR])
      const lo = d3.min(rows, (r) => d3.min(r.points, (p) => p.index))
      const hi = d3.max(rows, (r) => d3.max(r.points, (p) => p.index))
      const y = d3.scaleLinear()
        .domain([Math.min(90, lo - 2), Math.max(110, hi + 2)])
        .range([height - 34, 14])

      sel.append('g').attr('transform', `translate(${left},0)`)
        .call(d3.axisLeft(y).ticks(5)).attr('class', 'axis')
      // 100 is where every country starts, so the line is the comparison.
      sel.append('line').attr('x1', left).attr('x2', plotR)
        .attr('y1', y(100)).attr('y2', y(100))
        .attr('stroke', 'currentColor').attr('opacity', 0.25)
        .attr('stroke-dasharray', '3 3')

      const line = d3.line().x((p, i) => x(i)).y((p) => y(p.index))
      rows.forEach((row, ri) => {
        sel.append('path').datum(row.points).attr('fill', 'none')
          .attr('stroke', countryColour(row.country)).attr('stroke-width', 2)
          .attr('d', line)
        row.points.forEach((p, i) => {
          const dot = sel.append('circle').attr('cx', x(i)).attr('cy', y(p.index))
            .attr('r', 3).attr('fill', countryColour(row.country))
          hoverable(dot, () => ({
            title: row.country,
            lines: [
              `${monthLabel(p.month)}: index ${p.index.toFixed(1)}`,
              `median ${Math.round(p.median).toLocaleString()} local`,
              `${p.n.toLocaleString()} postings stated a figure`
            ]
          }))
        })
      })
      legend(sel, plotR + 16, 16, rows.map((r) => ({
        label: `${r.country} ${r.trend.perMonth >= 0 ? '+' : ''}`
          + `${r.trend.perMonth.toFixed(1)}/mo · R² ${r.trend.r2.toFixed(2)}`,
        colour: countryColour(r.country)
      })))
    }

    /** Diverging bars: who lost ground and who gained it. */
    function drawDowntrend() {
      if (!downSvg.value) {
        return
      }
      const rows = trendByRegion(data.regionSeries, MIN_REGION_POSTINGS)
      if (!rows.length) {
        return
      }
      const left = 160
      const top = 14
      const barH = 20
      const { sel, width } = frame(downSvg.value, top + rows.length * barH + 24)
      const extent = d3.max(rows, (r) => Math.abs(r.perMonth)) || 0.01
      const mid = left + (Math.max(left + 80, width - 90) - left) / 2
      const x = d3.scaleLinear().domain([-extent, extent])
        .range([left, Math.max(left + 80, width - 90)])

      sel.append('line').attr('x1', mid).attr('x2', mid)
        .attr('y1', top - 4).attr('y2', top + rows.length * barH)
        .attr('stroke', 'currentColor').attr('opacity', 0.3)

      rows.forEach((row, i) => {
        const yy = top + i * barH
        const from = Math.min(x(0), x(row.perMonth))
        const to = Math.max(x(0), x(row.perMonth))
        sel.append('text').attr('x', left - 10).attr('y', yy + 14)
          .attr('text-anchor', 'end').attr('class', 'lbl').text(row.region)
        const rect = sel.append('rect').attr('x', from).attr('y', yy + 3)
          .attr('width', Math.max(1, to - from)).attr('height', barH - 8)
          .attr('fill', row.perMonth < 0 ? '#d1615d' : '#59a14f')
        hoverable(rect, () => ({
          title: row.region,
          lines: [
            `${row.perMonth >= 0 ? '+' : ''}`
              + `${(row.perMonth * 100).toFixed(2)}% of its own share a month`,
            `mean share ${(row.mean * 100).toFixed(2)}%`,
            `R² ${row.r2.toFixed(2)} · ${row.total.toLocaleString()} postings`
          ]
        }))
        sel.append('text').attr('x', to + 8).attr('y', yy + 14)
          .attr('class', 'val')
          .text(`${row.perMonth >= 0 ? '+' : ''}`
            + `${(row.perMonth * 100).toFixed(1)}%`)
      })
    }

    /** Full-width stacked bars: the tier mix, country by country. */
    function drawSkills() {
      if (!skillSvg.value || !(data.skills.buckets || []).length) {
        return
      }
      const rows = data.skills.buckets
      const left = 140
      const top = 14
      const barH = 30
      const { sel, width } = frame(
        skillSvg.value, top + rows.length * barH + 44)
      const right = Math.max(left + 80, width - 40)

      rows.forEach((row, i) => {
        const yy = top + i * barH
        const mix = skillMix(row)
        sel.append('text').attr('x', left - 10).attr('y', yy + 18)
          .attr('text-anchor', 'end').attr('class', 'lbl').text(row.val)
        let cursor = left
        mix.forEach((m, mi) => {
          const w = (right - left) * m.share
          const rect = sel.append('rect').attr('x', cursor).attr('y', yy + 3)
            .attr('width', Math.max(0, w)).attr('height', barH - 10)
            .attr('fill', tierColour(m.key))
          hoverable(rect, () => ({
            title: `${row.val} · ${SKILL_TIERS[mi].label}`,
            lines: [
              `${(m.share * 100).toFixed(1)}% of matched titles`,
              `${m.count.toLocaleString()} postings`
            ]
          }))
          if (w > 46) {
            sel.append('text').attr('x', cursor + w / 2).attr('y', yy + 18)
              .attr('text-anchor', 'middle').attr('class', 'inbar')
              .text(`${Math.round(m.share * 100)}%`)
          }
          cursor += w
        })
      })
      legend(sel, left, top + rows.length * barH + 8,
        SKILL_TIERS.map((t) => ({ label: t.label, colour: tierColour(t.key) })))
    }

    /** Lollipops: mean posting life per region, against the corpus mean. */
    function drawFill() {
      if (!fillSvg.value || !data.lives.length) {
        return
      }
      const rows = data.lives.slice()
        .map((b) => ({ region: b.val, days: b.days || 0, n: b.count || 0 }))
        .sort((a, b) => b.days - a.days)
      const left = 160
      const top = 16
      const barH = 20
      const { sel, width } = frame(fillSvg.value, top + rows.length * barH + 26)
      const right = Math.max(left + 80, width - 90)
      const max = d3.max(rows, (r) => r.days) || 1
      const x = d3.scaleLinear().domain([0, max * 1.1]).range([left, right])
      const mean = d3.mean(rows, (r) => r.days) || 0

      sel.append('line').attr('x1', x(mean)).attr('x2', x(mean))
        .attr('y1', top - 6).attr('y2', top + rows.length * barH)
        .attr('stroke', 'currentColor').attr('opacity', 0.35)
        .attr('stroke-dasharray', '3 3')
      sel.append('text').attr('x', x(mean)).attr('y', top - 10)
        .attr('text-anchor', 'middle').attr('class', 'tick')
        .text(`mean ${mean.toFixed(1)}d`)

      rows.forEach((row, i) => {
        const yy = top + i * barH + (barH - 8) / 2
        sel.append('text').attr('x', left - 10).attr('y', yy + 4)
          .attr('text-anchor', 'end').attr('class', 'lbl').text(row.region)
        sel.append('line').attr('x1', x(0)).attr('x2', x(row.days))
          .attr('y1', yy).attr('y2', yy)
          .attr('stroke', 'currentColor').attr('opacity', 0.25)
        const dot = sel.append('circle').attr('cx', x(row.days)).attr('cy', yy)
          .attr('r', 5).attr('fill', '#4e79a7')
        hoverable(dot, () => ({
          title: row.region,
          lines: [`${row.days.toFixed(1)} days on average`,
                  `${row.n.toLocaleString()} distinct jobs`]
        }))
        sel.append('text').attr('x', x(row.days) + 10).attr('y', yy + 4)
          .attr('class', 'val').text(`${row.days.toFixed(1)}d`)
      })
    }

    /** Transport and logistics as a share of each country, over time. */
    function drawTransport() {
      if (!transportSvg.value || !data.months.length) {
        return
      }
      const height = 260
      const left = 54
      const right = 150
      const { sel, width } = frame(transportSvg.value, height)
      const plotR = Math.max(left + 60, width - right)
      const x = d3.scaleLinear().domain([0, data.months.length - 1])
        .range([left, plotR])
      const points = data.months.map((b, i) => ({
        i,
        y: b.count ? ((b.transport || {}).count || 0) / b.count : 0,
        val: b.val
      }))
      const max = d3.max(points, (p) => p.y) || 0.01
      const y = d3.scaleLinear().domain([0, max * 1.2]).range([height - 34, 14])

      sel.append('g').attr('transform', `translate(${left},0)`)
        .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.1%')))
        .attr('class', 'axis')
      data.months.forEach((b, i) => {
        if (i % 3 === 0) {
          sel.append('text').attr('x', x(i)).attr('y', height - 16)
            .attr('text-anchor', 'middle').attr('class', 'tick')
            .text(monthLabel(b.val))
        }
      })
      const area = d3.area().x((p) => x(p.i)).y0(y(0)).y1((p) => y(p.y))
      sel.append('path').datum(points).attr('fill', '#4e79a7')
        .attr('opacity', 0.18).attr('d', area)
      sel.append('path').datum(points).attr('fill', 'none')
        .attr('stroke', '#4e79a7').attr('stroke-width', 2)
        .attr('d', d3.line().x((p) => x(p.i)).y((p) => y(p.y)))
      points.forEach((p) => {
        const dot = sel.append('circle').attr('cx', x(p.i)).attr('cy', y(p.y))
          .attr('r', 3).attr('fill', '#4e79a7')
        hoverable(dot, () => ({
          title: monthLabel(p.val),
          lines: [`${(p.y * 100).toFixed(2)}% of the month's postings`]
        }))
      })
      const fit = salaryTrend(points.map((p) => ({ index: p.y })))
      legend(sel, plotR + 16, 20, [{
        label: `${fit.perMonth >= 0 ? '+' : ''}`
          + `${(fit.perMonth * 100).toFixed(3)}%/mo · R² ${fit.r2.toFixed(2)}`,
        colour: '#4e79a7'
      }])
    }

    /** One line per calendar year, so the reader sees how little there is. */
    function drawSeason() {
      if (!seasonSvg.value || !data.months.length) {
        return
      }
      const years = byCalendarMonth(data.months, 'transport')
      const height = 280
      const left = 54
      const right = 130
      const { sel, width } = frame(seasonSvg.value, height)
      const plotR = Math.max(left + 60, width - right)
      const x = d3.scalePoint().domain(d3.range(1, 13)).range([left, plotR])
      const max = d3.max(years, (yr) => d3.max(yr.points, (p) => p.share)) || 0.01
      const y = d3.scaleLinear().domain([0, max * 1.2]).range([height - 34, 14])

      sel.append('g').attr('transform', `translate(${left},0)`)
        .call(d3.axisLeft(y).ticks(5).tickFormat(d3.format('.1%')))
        .attr('class', 'axis')
      MONTH_NAMES.forEach((name, i) => {
        sel.append('text').attr('x', x(i + 1)).attr('y', height - 16)
          .attr('text-anchor', 'middle').attr('class', 'tick').text(name)
      })
      const line = d3.line().x((p) => x(p.month)).y((p) => y(p.share))
      years.forEach((yr, i) => {
        sel.append('path').datum(yr.points).attr('fill', 'none')
          .attr('stroke', firmColour(i)).attr('stroke-width', 2).attr('d', line)
        yr.points.forEach((p) => {
          const dot = sel.append('circle').attr('cx', x(p.month))
            .attr('cy', y(p.share)).attr('r', 3.5).attr('fill', firmColour(i))
          hoverable(dot, () => ({
            title: `${MONTH_NAMES[p.month - 1]} ${yr.year}`,
            lines: [`${(p.share * 100).toFixed(2)}% transport and logistics`,
                    `${p.count.toLocaleString()} of `
                    + `${p.total.toLocaleString()} postings`]
          }))
        })
      })
      legend(sel, plotR + 16, 20, years.map((yr, i) => ({
        label: `${yr.year} · ${yr.points.length} month`
          + `${yr.points.length === 1 ? '' : 's'}`,
        colour: firmColour(i)
      })))
    }

    /** Heatmap: residual from each region's own line, in sigmas. */
    function drawAnomalies() {
      if (!anomalySvg.value || !(data.anomalyRows || []).length) {
        return
      }
      const rows = data.anomalyRows
      const labels = data.anomalyLabels
      const left = 160
      const top = 30
      const cellH = 20
      const { sel, width } = frame(
        anomalySvg.value, top + rows.length * cellH + 40)
      const right = Math.max(left + 120, width - 30)
      const cellW = (right - left) / labels.length
      const scale = d3.scaleLinear()
        .domain([-3, 0, 3])
        .range(['#d1615d', '#f2f2f2', '#4e79a7'])
        .clamp(true)

      labels.forEach((label, i) => {
        if (i % 2 === 0) {
          sel.append('text').attr('x', left + i * cellW + cellW / 2)
            .attr('y', top - 10).attr('text-anchor', 'middle')
            .attr('class', 'tick').text(label.replace(/ \d{4}$/, ''))
        }
      })
      rows.forEach((row, r) => {
        const yy = top + r * cellH
        sel.append('text').attr('x', left - 10).attr('y', yy + 14)
          .attr('text-anchor', 'end').attr('class', 'lbl').text(row.region)
        row.z.forEach((z, i) => {
          const cell = sel.append('rect')
            .attr('x', left + i * cellW).attr('y', yy + 1)
            .attr('width', Math.max(1, cellW - 1)).attr('height', cellH - 2)
            .attr('fill', scale(z))
          if (Math.abs(z) >= ANOMALY_THRESHOLD) {
            cell.attr('stroke', '#1a1410').attr('stroke-width', 1.2)
          }
          hoverable(cell, () => ({
            title: `${row.region} · ${labels[i]}`,
            lines: [`${z >= 0 ? '+' : ''}${z.toFixed(2)} standard deviations`,
                    Math.abs(z) >= ANOMALY_THRESHOLD
                      ? 'past the threshold' : 'within its trend']
          }))
        })
      })
      const key = sel.append('g')
        .attr('transform', `translate(${left},${top + rows.length * cellH + 16})`)
      ;[-3, -2, -1, 0, 1, 2, 3].forEach((z, i) => {
        key.append('rect').attr('x', i * 34).attr('width', 32).attr('height', 10)
          .attr('fill', scale(z))
        key.append('text').attr('x', i * 34 + 16).attr('y', 22)
          .attr('text-anchor', 'middle').attr('class', 'tick')
          .text(z > 0 ? `+${z}` : z)
      })
    }

    onMounted(() => {
      load()
      if (typeof ResizeObserver !== 'undefined' && root.value) {
        observer = new ResizeObserver(() => {
          // Only on a real width change. A ResizeObserver that redraws on
          // every callback feeds its own next callback.
          const now = root.value ? Math.round(root.value.clientWidth) : 0
          if (!loading.value && now && Math.abs(now - drawnAt) > 8) {
            redraw()
          }
        })
        observer.observe(root.value)
      }
    })
    onUnmounted(() => {
      if (observer) {
        observer.disconnect()
        observer = null
      }
    })

    return {
      root, firmsSvg, firmTrendSvg, salarySvg, downSvg, skillSvg, fillSvg,
      transportSvg, seasonSvg, anomalySvg,
      loading, error, tip, sectorField, firms, companyCount, hhi, territorial,
      salarySeries, salaryShare, lifeOverRows, lifeCollapsed, anomalyLine,
      minRegion, minSalary, threshold, failed, countryShare
    }
  }
}
</script>

<style scoped>
/* The same card as the panels above, because it is the same list. These
   were a second design -- currentColor on a transparent ground, a 62rem
   measure, their own margins -- which on the paper coloured page read as
   nine panels that had lost their background. The values here are copied
   from AnalyticsPanel deliberately: one look, one list. */
.challenges { display: flex; flex-direction: column; gap: 18px;
              position: relative; }
.card { background: #fff; border: 1px solid #e2e6ea; border-radius: 6px;
        padding: 14px 16px; }
.card h3 { margin: 0 0 2px; font-size: 1.02rem; }
.q { margin: 0 0 10px; font-size: 0.8rem; color: #7a8691;
     text-transform: uppercase; letter-spacing: 0.03em; }
.chart { display: block; width: 100%; overflow: visible; }
.note { margin: 10px 0 0; font-size: 0.86rem; color: #55606b; }
.loading { color: #7a8691; margin: 0; }
.caveat { margin: 0 0 10px; padding: 8px 10px; font-size: 0.84rem;
          color: #6b4b12; background: #fdf3e0; border-left: 3px solid #e1a03c;
          border-radius: 3px; }
.caveat.partial { background: #fff; border: 1px solid #e2e6ea;
                  border-left: 3px solid #e1a03c; border-radius: 6px;
                  padding: 14px 16px; color: #55606b; }
.banner { background: #fdecea; border-color: #f5c6c0; color: #8a2c22; }
.tip { position: absolute; z-index: 20; pointer-events: none;
       background: #1f2933; color: #f5f7fa; border-radius: 4px;
       padding: 7px 9px; font-size: 0.78rem; line-height: 1.35;
       box-shadow: 0 3px 12px rgba(0,0,0,0.22); max-width: 300px; }
.tip strong { display: block; margin-bottom: 2px; }
.tip span { display: block; opacity: 0.85; }
</style>

<style>
/* Not scoped: these land on nodes d3 appends, which carry no scope id. */
.challenges .lbl { font-size: 11.5px; fill: #55606b; }
.challenges .val { font-size: 11px; fill: #7a8691;
                   font-variant-numeric: tabular-nums; }
.challenges .tick { font-size: 10.5px; fill: #7a8691; }
.challenges .leg { font-size: 11px; fill: #55606b; }
.challenges .inbar { font-size: 10.5px; fill: #fff; font-weight: 600; }
.challenges .axis text { font-size: 10.5px; fill: #7a8691; }
.challenges .axis path, .challenges .axis line { stroke: #d7dde3; }
</style>
