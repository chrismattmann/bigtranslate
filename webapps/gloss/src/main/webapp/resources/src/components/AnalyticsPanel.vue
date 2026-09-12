<template>
  <section class="analytics">
    <header class="intro">
      <h2>Analytics</h2>
      <p>
        The XDATA employment dataset ships with a list of challenge questions.
        These are the ones this index can answer, each panel named for its
        question and drawn from the corpus rather than a sample.
      </p>
      <p v-if="sectorField === 'text'" class="caveat">
        Sectors are matched against the catch-all <code>text</code> field,
        which copies every column, so a match may have come from a company
        name rather than a job title. A tokenised <code>title_txt</code> is in
        the schema and takes effect on the next re-index; these panels will
        use it automatically.
      </p>
    </header>

    <p v-if="error" class="banner">{{ error }}</p>
    <p v-else-if="loading" class="loading">Asking Solr…</p>

    <template v-else>
      <!-- Q12 -->
      <article class="card">
        <h3>Full time against part time, over the collection</h3>
        <p class="q">Challenge 12 · trends in full time vs part time employment</p>
        <svg ref="hoursSvg" class="chart"></svg>
        <p class="note">
          Share of each month's postings. <strong>{{ months.length }}</strong>
          whole months, {{ monthRange }}. The job type is a controlled
          vocabulary the pipeline translated, so this is a count rather than
          an inference.
        </p>
      </article>

      <!-- Q2 / Q10 -->
      <article class="card">
        <h3>How long a posting stays up</h3>
        <p class="q">Challenge 2 and 10 · how long postings last, and how quickly jobs fill</p>
        <svg ref="lifeSvg" class="chart"></svg>
        <p class="note">
          Mean days between first and last seen, per job type, across all
          {{ totalLabel }} postings. A posting stops being re-seen when it
          comes down, so this is how long it was up rather than how long the
          job took to fill.
        </p>
      </article>

      <!-- Q14 -->
      <article class="card">
        <h3>What each place advertises for</h3>
        <p class="q">Challenge 14 · classify and zone places by their jobs</p>
        <svg ref="zoneSvg" class="chart"></svg>
        <p class="note">
          Sector mix per region, largest first. The label on the right is the
          leading sector and the figure after it is how far ahead of the next
          one it is: a narrow margin means the region has a mix, not a
          character.
        </p>
      </article>

      <!-- Q1 -->
      <article class="card">
        <h3>Where each sector is heading</h3>
        <p class="q">Challenge 1 · which areas will have which job types</p>
        <svg ref="trendSvg" class="chart"></svg>
        <p class="note">
          Monthly postings per sector, with a
          <strong>straight line through {{ months.length }} points</strong>
          continued three months dashed. It is a projection, not a forecast:
          no seasonality, no saturation, and no notion that a job market can
          turn. R² is printed against each so a bad fit looks like one.
        </p>
      </article>

      <!-- Q5 -->
      <article class="card">
        <h3>Sectors growing everywhere but thin here</h3>
        <p class="q">Challenge 5 · where new business domains might succeed</p>
        <svg ref="gapSvg" class="chart"></svg>
        <p class="note">
          A cell is dark where a sector is growing across the corpus and is
          under-represented in that region. Score is the shortfall against the
          corpus-wide share multiplied by that sector's growth, so a sector
          that is booming and already saturated locally scores nothing, and so
          does one that is absent and going nowhere. Regions under
          {{ minRegion }} postings are left out, because a handful of postings
          is a shortfall in every sector at once.
        </p>
      </article>
    </template>
  </section>
</template>

<script>
import { onMounted, onUnmounted, ref } from 'vue'
import * as d3 from 'd3'
import { solrFacet } from '../api.js'
import {
  MIN_REGION_POSTINGS, SECTORS, SECTOR_FIELDS, growthRate, monthLabel,
  opportunities, project, sectorCounts, sectorFacet, sectorShares,
  wholeMonths, zone
} from '../analytics.js'

const REGION_LIMIT = 12
const PROJECT_MONTHS = 3
const HOUR_TYPES = ['Full Time', 'Part Time', 'Hourly', 'Temporary',
                    'Internship']

export default {
  name: 'AnalyticsPanel',
  setup() {
    const hoursSvg = ref(null)
    const lifeSvg = ref(null)
    const zoneSvg = ref(null)
    const trendSvg = ref(null)
    const gapSvg = ref(null)
    const loading = ref(true)
    const error = ref('')
    const months = ref([])
    const monthRange = ref('')
    const totalLabel = ref('')
    const sectorField = ref(SECTOR_FIELDS.broad)
    const minRegion = MIN_REGION_POSTINGS.toLocaleString()
    let observer = null

    const colour = d3.scaleOrdinal()
      .domain(SECTORS.map((s) => s.key))
      .range(d3.schemeTableau10.concat(['#9c755f']))

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

    async function load() {
      loading.value = true
      error.value = ''
      try {
        await pickSectorField()
        const field = sectorField.value

        const span = await solrFacet(
          { lo: 'min(postedDate)', hi: 'max(postedDate)' })
        const lo = (span.facets.lo || '2012-01-01T00:00:00Z').slice(0, 10)
        const hi = (span.facets.hi || '2014-01-01T00:00:00Z').slice(0, 10)
        totalLabel.value = (span.facets.count || 0).toLocaleString()

        const byMonth = {
          type: 'range',
          field: 'postedDate',
          start: `${lo.slice(0, 7)}-01T00:00:00Z`,
          end: `${hi.slice(0, 7)}-28T00:00:00Z`,
          gap: '+1MONTH',
          mincount: 1,
          facet: Object.assign(
            sectorFacet(field),
            HOUR_TYPES.reduce((acc, t) => {
              acc[t] = { type: 'query', q: `jobtype:"${t}"` }
              return acc
            }, {}))
        }

        const lifetime = {
          type: 'terms',
          field: 'jobtype',
          limit: 6,
          facet: { days: 'avg(div(ms(lastSeenDate,firstSeenDate),86400000))' }
        }

        const byRegion = {
          type: 'terms',
          field: 'department',
          limit: REGION_LIMIT,
          facet: sectorFacet(field)
        }

        const answer = await solrFacet({
          months: byMonth,
          life: lifetime,
          regions: byRegion,
          national: { type: 'query', q: '*:*', facet: sectorFacet(field) }
        })

        const f = answer.facets || {}
        months.value = wholeMonths((f.months && f.months.buckets) || [])
        if (months.value.length) {
          monthRange.value = `${monthLabel(months.value[0].val)} to `
            + `${monthLabel(months.value[months.value.length - 1].val)}`
        }

        drawHours(months.value)
        drawLifetimes(((f.life && f.life.buckets) || []))
        const regions = ((f.regions && f.regions.buckets) || []).map((b) => ({
          name: b.val,
          total: b.count,
          counts: sectorCounts(b)
        }))
        drawZones(regions)
        drawTrends(months.value)
        drawGaps(regions, months.value, sectorShares(sectorCounts(f.national)))
      } catch (e) {
        error.value = e && e.message ? e.message : String(e)
      } finally {
        loading.value = false
      }
    }

    /** A chart frame sized to whatever room the card has. */
    function frame(node, height) {
      const width = Math.max(360, (node.parentNode || {}).clientWidth || 720)
      const sel = d3.select(node)
      sel.selectAll('*').remove()
      sel.attr('viewBox', `0 0 ${width} ${height}`)
        .attr('width', '100%')
        .attr('height', height)
      return { sel, width, height }
    }

    function drawHours(buckets) {
      if (!hoursSvg.value || !buckets.length) {
        return
      }
      const m = { top: 12, right: 128, bottom: 28, left: 44 }
      const { sel, width, height } = frame(hoursSvg.value, 240)
      const rows = buckets.map((b) => {
        const row = { label: monthLabel(b.val) }
        const total = HOUR_TYPES.reduce(
          (sum, t) => sum + ((b[t] && b[t].count) || 0), 0)
        HOUR_TYPES.forEach((t) => {
          row[t] = total ? ((b[t] && b[t].count) || 0) / total : 0
        })
        return row
      })
      const x = d3.scalePoint()
        .domain(rows.map((r) => r.label))
        .range([m.left, width - m.right])
      const y = d3.scaleLinear().domain([0, 1]).range([height - m.bottom, m.top])
      const stack = d3.stack().keys(HOUR_TYPES)(rows)
      const area = d3.area()
        .x((d, i) => x(rows[i].label))
        .y0((d) => y(d[0]))
        .y1((d) => y(d[1]))
        .curve(d3.curveMonotoneX)

      sel.append('g').selectAll('path').data(stack).join('path')
        .attr('fill', (d, i) => d3.schemeTableau10[i])
        .attr('opacity', 0.88)
        .attr('d', area)

      sel.append('g').attr('transform', `translate(0,${height - m.bottom})`)
        .call(d3.axisBottom(x).tickValues(
          rows.filter((r, i) => i % 3 === 0).map((r) => r.label)))
      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y).ticks(4).tickFormat(d3.format('.0%')))

      const legend = sel.append('g')
        .attr('transform', `translate(${width - m.right + 12},${m.top})`)
      HOUR_TYPES.forEach((t, i) => {
        const row = legend.append('g').attr('transform', `translate(0,${i * 18})`)
        row.append('rect').attr('width', 11).attr('height', 11)
          .attr('fill', d3.schemeTableau10[i])
        row.append('text').attr('x', 16).attr('y', 10)
          .attr('class', 'leg').text(t)
      })
    }

    function drawLifetimes(buckets) {
      if (!lifeSvg.value || !buckets.length) {
        return
      }
      const rows = buckets
        .filter((b) => typeof b.days === 'number')
        .map((b) => ({ label: b.val, days: b.days, n: b.count }))
        .sort((a, b) => b.days - a.days)
      if (!rows.length) {
        return
      }
      const m = { top: 10, right: 96, bottom: 28, left: 168 }
      const height = rows.length * 26 + m.top + m.bottom
      const { sel, width } = frame(lifeSvg.value, height)
      const x = d3.scaleLinear()
        .domain([0, d3.max(rows, (r) => r.days) * 1.15])
        .range([m.left, width - m.right])
      const y = d3.scaleBand()
        .domain(rows.map((r) => r.label))
        .range([m.top, height - m.bottom]).padding(0.24)

      sel.append('g').selectAll('rect').data(rows).join('rect')
        .attr('x', m.left).attr('y', (r) => y(r.label))
        .attr('width', (r) => x(r.days) - m.left)
        .attr('height', y.bandwidth())
        .attr('fill', '#4e79a7')
      sel.append('g').selectAll('text').data(rows).join('text')
        .attr('x', (r) => x(r.days) + 8)
        .attr('y', (r) => y(r.label) + y.bandwidth() / 2 + 4)
        .attr('class', 'val')
        .text((r) => `${r.days.toFixed(1)} days`)
      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y))
      sel.append('g').attr('transform', `translate(0,${height - m.bottom})`)
        .call(d3.axisBottom(x).ticks(6))
    }

    function drawZones(regions) {
      if (!zoneSvg.value || !regions.length) {
        return
      }
      const rows = regions
        .map((r) => ({ name: r.name, z: zone(r.counts),
                       shares: sectorShares(r.counts), total: r.total }))
        .filter((r) => r.shares.total > 0)
      if (!rows.length) {
        return
      }
      const m = { top: 10, right: 210, bottom: 28, left: 150 }
      const height = rows.length * 28 + m.top + m.bottom
      const { sel, width } = frame(zoneSvg.value, height)
      const x = d3.scaleLinear().domain([0, 1]).range([m.left, width - m.right])
      const y = d3.scaleBand().domain(rows.map((r) => r.name))
        .range([m.top, height - m.bottom]).padding(0.24)

      rows.forEach((row) => {
        let acc = 0
        const g = sel.append('g')
        SECTORS.forEach((s) => {
          const share = row.shares[s.key] || 0
          if (share <= 0) {
            return
          }
          g.append('rect')
            .attr('x', x(acc)).attr('y', y(row.name))
            .attr('width', Math.max(0, x(acc + share) - x(acc)))
            .attr('height', y.bandwidth())
            .attr('fill', colour(s.key))
            .append('title')
            .text(`${row.name} · ${s.label} · ${(share * 100).toFixed(1)}%`)
          acc += share
        })
        sel.append('text')
          .attr('x', width - m.right + 10)
          .attr('y', y(row.name) + y.bandwidth() / 2 + 4)
          .attr('class', 'val')
          .text(`${row.z.label} +${(row.z.margin * 100).toFixed(0)}`)
      })
      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y))
      sel.append('g').attr('transform', `translate(0,${height - m.bottom})`)
        .call(d3.axisBottom(x).ticks(5).tickFormat(d3.format('.0%')))
    }

    function drawTrends(buckets) {
      if (!trendSvg.value || buckets.length < 3) {
        return
      }
      const series = SECTORS.map((s) => ({
        key: s.key,
        label: s.label,
        values: buckets.map((b) => (b[s.key] && b[s.key].count) || 0)
      })).filter((s) => d3.sum(s.values) > 0)
      if (!series.length) {
        return
      }
      const cols = 3
      const rows = Math.ceil(series.length / cols)
      const cellH = 92
      const { sel, width, height } = frame(trendSvg.value, rows * cellH + 20)
      const cellW = width / cols

      series.forEach((s, i) => {
        const { fit, projected } = project(s.values, PROJECT_MONTHS)
        const all = s.values.concat(projected)
        const gx = (i % cols) * cellW
        const gy = Math.floor(i / cols) * cellH
        const g = sel.append('g').attr('transform', `translate(${gx},${gy})`)
        const x = d3.scaleLinear().domain([0, all.length - 1])
          .range([56, cellW - 14])
        const y = d3.scaleLinear().domain([0, d3.max(all) || 1])
          .range([cellH - 26, 14])
        const line = d3.line().x((d, k) => x(k)).y((d) => y(d))

        g.append('path').datum(s.values)
          .attr('fill', 'none').attr('stroke', colour(s.key))
          .attr('stroke-width', 2).attr('d', line)
        g.append('path')
          .datum(s.values.slice(-1).concat(projected))
          .attr('fill', 'none').attr('stroke', colour(s.key))
          .attr('stroke-width', 2).attr('stroke-dasharray', '4 3')
          .attr('opacity', 0.75)
          .attr('d', d3.line()
            .x((d, k) => x(s.values.length - 1 + k)).y((d) => y(d)))
        g.append('text').attr('x', 0).attr('y', 16)
          .attr('class', 'small').text(s.label)
        g.append('text').attr('x', 0).attr('y', 30)
          .attr('class', 'tiny')
          .text(`R² ${fit.r2.toFixed(2)}`)
      })
    }

    function drawGaps(regions, buckets, national) {
      if (!gapSvg.value || !regions.length || buckets.length < 3) {
        return
      }
      const growth = {}
      SECTORS.forEach((s) => {
        growth[s.key] = growthRate(
          buckets.map((b) => (b[s.key] && b[s.key].count) || 0))
      })
      const found = opportunities(regions, national, growth)
      if (!found.length) {
        return
      }
      const names = regions
        .filter((r) => r.total >= MIN_REGION_POSTINGS)
        .map((r) => r.name)
      const m = { top: 78, right: 16, bottom: 16, left: 150 }
      const height = names.length * 24 + m.top + m.bottom
      const { sel, width } = frame(gapSvg.value, height)
      const x = d3.scaleBand().domain(SECTORS.map((s) => s.key))
        .range([m.left, width - m.right]).padding(0.06)
      const y = d3.scaleBand().domain(names)
        .range([m.top, height - m.bottom]).padding(0.06)
      const shade = d3.scaleSequential(d3.interpolateYlGnBu)
        .domain([0, d3.max(found, (o) => o.score) || 1])

      const index = {}
      found.forEach((o) => { index[`${o.region}|${o.sector}`] = o })

      names.forEach((name) => {
        SECTORS.forEach((s) => {
          const hit = index[`${name}|${s.key}`]
          sel.append('rect')
            .attr('x', x(s.key)).attr('y', y(name))
            .attr('width', x.bandwidth()).attr('height', y.bandwidth())
            .attr('fill', hit ? shade(hit.score) : '#f2f2f2')
            .append('title')
            .text(hit
              ? `${name} · ${hit.label}\n`
                + `here ${(hit.local * 100).toFixed(1)}% against `
                + `${(hit.national * 100).toFixed(1)}% everywhere\n`
                + `sector growth ${(hit.growth * 100).toFixed(1)}% a month`
              : `${name} · ${s.label}\nno opening: already here, or not growing`)
        })
      })
      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y))
      sel.append('g').attr('transform', `translate(0,${m.top})`)
        .call(d3.axisTop(x).tickFormat((k) => {
          const s = SECTORS.find((c) => c.key === k)
          return s ? s.label : k
        }))
        .selectAll('text')
        .attr('transform', 'rotate(-38)')
        .style('text-anchor', 'start')
    }

    onMounted(() => {
      load()
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(() => {
          if (!loading.value && !error.value) {
            load()
          }
        })
        if (hoursSvg.value && hoursSvg.value.parentNode) {
          observer.observe(hoursSvg.value.parentNode)
        }
      }
    })
    onUnmounted(() => {
      if (observer) {
        observer.disconnect()
      }
    })

    return {
      hoursSvg, lifeSvg, zoneSvg, trendSvg, gapSvg,
      loading, error, months, monthRange, totalLabel, sectorField, minRegion
    }
  }
}
</script>

<style scoped>
.analytics { display: flex; flex-direction: column; gap: 18px; }
.intro h2 { margin: 0 0 4px; }
.intro p { margin: 0 0 6px; color: #55606b; max-width: 74ch; }
.caveat { font-size: 0.86rem; background: #fff8e6; border-left: 3px solid #d9a441;
          padding: 8px 10px; border-radius: 3px; }
.caveat code { background: #f3ecd8; padding: 0 3px; border-radius: 2px; }
.card { background: #fff; border: 1px solid #e2e6ea; border-radius: 6px;
        padding: 14px 16px; }
.card h3 { margin: 0 0 2px; font-size: 1.02rem; }
.q { margin: 0 0 10px; font-size: 0.8rem; color: #7a8691;
     text-transform: uppercase; letter-spacing: 0.03em; }
.chart { display: block; width: 100%; overflow: visible; }
.note { margin: 10px 0 0; font-size: 0.86rem; color: #55606b; max-width: 82ch; }
.loading { color: #7a8691; }
.banner { background: #fdecea; border: 1px solid #f5c2bd; border-radius: 4px;
          padding: 8px 10px; }
:deep(.leg), :deep(.val) { font-size: 11px; fill: #3d464f; }
:deep(.small) { font-size: 11px; fill: #3d464f; font-weight: 600; }
:deep(.tiny) { font-size: 10px; fill: #8a949d; }
</style>
