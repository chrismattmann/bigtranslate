<template>
  <section class="analytics" ref="root">
    <header class="intro">
      <h2>Analytics</h2>
      <p>
        Job postings from <strong>computrabajo.com</strong> affiliate sites,
        which serve Mexico and South America: Argentina, Colombia, the
        Dominican Republic, Honduras, Mexico, Peru and Venezuela. Postings are
        temporary and come down without notice, so the corpus is an attempt at
        persisting them long enough to be analysed. Almost all of it was
        written in Spanish; the columns below are readable because the
        pipeline translated them.
      </p>
      <p>
        <strong>{{ totalLabel }}</strong> rows over
        <strong>{{ jobLabel }}</strong> distinct jobs, {{ monthRange }}. Every
        page of every affiliate site was parsed once a day: a posting's first
        and last seen dates are set when it first appears, and the last seen
        date is updated on each day it is still there. So a job appears once
        per day it was up, about 57 times on average, and the two numbers
        above are not the same question. Panels say which one they counted.
      </p>
      <p>
        The dataset ships with a list of challenge questions. These are the
        ones this index can answer on its own; the others need data we do not
        have here, such as joining posting URLs against the WDC hyperlink
        graph or correlating against Twitter.
      </p>
      <p v-if="sectorField === 'text'" class="caveat">
        Sectors are matched against the catch-all <code>text</code> field,
        which copies every column, so a match may have come from a company
        name rather than a job title. A tokenised <code>title_txt</code> is in
        the schema and takes effect on the next re-index; these panels will
        use it automatically.
      </p>
    </header>

    <div v-if="tip" class="tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      <strong>{{ tip.title }}</strong>
      <span v-for="(line, i) in tip.lines" :key="i">{{ line }}</span>
    </div>

    <p v-if="error" class="banner">{{ error }}</p>
    <p v-else-if="loading" class="loading">Asking Solr…</p>

    <template v-else>
      <!-- Q12 -->
      <article class="card">
        <h3>Full time against part time, over the collection</h3>
        <p class="q">Challenge 12 · trends in full time vs part time employment</p>
        <svg ref="hoursSvg" class="chart"></svg>
        <p class="note">
          Share of each month's postings across
          <strong>{{ months.length }}</strong> whole months,
          {{ monthRange }}. The job type is a controlled vocabulary the
          pipeline translated, so this is a count rather than an inference.
          Partial months at either end are left out: the scrape began on
          31 July 2012 and stopped on 13 December 2013, so those buckets hold
          one day and thirteen.
        </p>
      </article>

      <!-- Q2 / Q10 -->
      <article class="card">
        <h3>How long a posting stays up</h3>
        <p class="q">Challenge 2 and 10 · how long postings last, and how quickly jobs fill</p>
        <svg ref="lifeSvg" class="chart"></svg>
        <p class="note">
          Mean days between first and last seen, per job type, over
          <strong>{{ jobLabel }} distinct jobs</strong> rather than over the
          {{ totalLabel }} rows. Those are very different numbers: a job is
          recorded once per day it was up, so averaging over rows weights
          every posting by its own length and answered about 100 days. One
          row per job answers about 13. A posting stops being re-seen when it
          comes down, so this is how long it stayed up, which is the nearest
          thing the data holds to how quickly it was filled.
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
          Each sector's share of the month, {{ monthRange }}, with a
          <strong>straight line through {{ months.length }} points</strong>
          continued three months dashed. Share rather than count, because the
          scrape wound down: counts fall for every sector at once and would
          draw nine lines sloping into the floor. It is a projection, not a forecast:
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
          under-represented in that region. Growth is measured on each
          sector's <em>share</em> of its month, not its count: the scrape
          wound down over the period, so raw counts fall about 7% a month for
          every sector at once and would show nothing growing anywhere. Score is the shortfall against the
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
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as d3 from 'd3'
import { solrFacet } from '../api.js'
import {
  MIN_REGION_POSTINGS, SECTORS, SECTOR_FIELDS, growthRate, monthLabel,
  opportunities, project, sectorCounts, sectorFacet, sectorShares,
  shareSeries, wholeMonths, zone
} from '../analytics.js'

const REGION_LIMIT = 12
const PROJECT_MONTHS = 3
const HOUR_TYPES = ['Full Time', 'Part Time', 'Hourly', 'Temporary',
                    'Internship']

export default {
  name: 'AnalyticsPanel',
  setup() {
    const root = ref(null)
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
    const jobLabel = ref('')
    const sectorField = ref(SECTOR_FIELDS.broad)
    const tip = ref(null)
    const minRegion = MIN_REGION_POSTINGS.toLocaleString()
    let observer = null
    // What the last fetch returned, so a resize redraws without asking
    // Solr again. The panels are a function of this and the frame width.
    let data = null
    // The width the charts were last drawn at; see the observer below.
    let drawnAt = 0

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



        const byRegion = {
          type: 'terms',
          field: 'department',
          limit: REGION_LIMIT,
          facet: sectorFacet(field)
        }

        // Two requests, because one of them has to see a different set of
        // rows. The corpus holds one row per day a posting was up -- 119
        // million rows over 2.1 million jobs, about 57 rows each -- so an
        // average over rows is weighted by how long each posting lasted:
        // a job up for two hundred days contributes two hundred rows each
        // saying two hundred days. Collapsing to one row per url answers the
        // question that was asked, and it costs two seconds.
        const [answer, lives] = await Promise.all([
          solrFacet({
            months: byMonth,
            regions: byRegion,
            national: { type: 'query', q: '*:*', facet: sectorFacet(field) }
          }),
          solrFacet({
            jobs: 'unique(url)',
            life: {
              type: 'terms',
              field: 'jobtype',
              limit: 6,
              facet: { days: 'avg(div(ms(lastSeenDate,firstSeenDate),86400000))' }
            }
          }, { fq: '{!collapse field=url}' })
        ])

        const f = answer.facets || {}
        const lf = lives.facets || {}
        jobLabel.value = (lf.jobs || 0).toLocaleString()
        months.value = wholeMonths((f.months && f.months.buckets) || [])
        if (months.value.length) {
          monthRange.value = `${monthLabel(months.value[0].val)} to `
            + `${monthLabel(months.value[months.value.length - 1].val)}`
        }

        data = {
          months: months.value,
          life: (lf.life && lf.life.buckets) || [],
          regions: ((f.regions && f.regions.buckets) || []).map((b) => ({
            name: b.val,
            total: b.count,
            counts: sectorCounts(b)
          })),
          national: sectorShares(sectorCounts(f.national))
        }
      } catch (e) {
        error.value = e && e.message ? e.message : String(e)
      } finally {
        loading.value = false
      }
      // After loading is false, not before. The svg elements live in the
      // template's v-else, so until Vue has flushed that update every ref is
      // null and every draw below returns having drawn nothing -- silently,
      // because a chart with no data to plot looks the same as one that was
      // never asked to.
      await nextTick()
      redraw()
    }

    function redraw() {
      if (!data || error.value) {
        return
      }
      drawnAt = root.value ? Math.round(root.value.clientWidth) : 0
      drawHours(data.months)
      drawLifetimes(data.life)
      drawZones(data.regions)
      drawTrends(data.months)
      drawGaps(data.regions, data.months, data.national)
    }

    /**
     * Hover, on every mark that stands for something.
     *
     * A stacked band and a shaded cell are the two shapes here that carry a
     * number nothing else shows: the colour says which sector and the width
     * says roughly how much, and "roughly how much" is not an answer. The
     * tooltip is the answer.
     */
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

    /**
     * The key, down the right of every chart.
     *
     * Nine colours and a label of "Office and admin +3" is not a chart
     * anybody can read: the reader has to be able to get from a band to a
     * sector without hovering it first.
     */
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

    /**
     * The nine sectors, laid out across the top rather than down the side.
     *
     * Nine rows down the right of a chart that is itself twelve rows tall
     * crowds it; across the top it wraps into two lines and stays out of the
     * way of the bars.
     */
    function sectorKey(sel, width, left) {
      const perRow = Math.max(3, Math.floor((width - left) / 168))
      SECTORS.forEach((s, i) => {
        const col = i % perRow
        const row = Math.floor(i / perRow)
        const g = sel.append('g')
          .attr('transform', `translate(${left + col * 168},${8 + row * 17})`)
        g.append('rect').attr('width', 11).attr('height', 11).attr('rx', 2)
          .attr('fill', colour(s.key))
        g.append('text').attr('x', 16).attr('y', 10)
          .attr('class', 'leg').text(s.label)
      })
      return Math.ceil(SECTORS.length / perRow) * 17 + 10
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

      // A band per month, invisible, so the whole column is hoverable rather
      // than only the pixel row where a particular type happens to sit.
      const step = (width - m.right - m.left) / Math.max(1, rows.length - 1)
      hoverable(
        sel.append('g').selectAll('rect').data(rows).join('rect')
          .attr('x', (r) => x(r.label) - step / 2)
          .attr('y', m.top)
          .attr('width', step)
          .attr('height', height - m.bottom - m.top)
          .attr('fill', 'transparent'),
        (r) => ({
          title: r.label,
          lines: HOUR_TYPES
            .filter((t) => r[t] > 0)
            .map((t) => `${t} ${(r[t] * 100).toFixed(1)}%`)
        }))

      legend(sel, width - m.right + 12, m.top, HOUR_TYPES.map((t, i) => ({
        label: t, colour: d3.schemeTableau10[i]
      })))
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

      hoverable(
        sel.append('g').selectAll('rect').data(rows).join('rect')
          .attr('x', m.left).attr('y', (r) => y(r.label))
          .attr('width', (r) => Math.max(0, x(r.days) - m.left))
          .attr('height', y.bandwidth())
          .attr('fill', '#4e79a7'),
        (r) => ({
          title: r.label,
          lines: [
            `${r.days.toFixed(1)} days up, on average`,
            `${r.n.toLocaleString()} distinct jobs`,
            'one row per job, not per day seen'
          ]
        }))
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
      const m = { top: 46, right: 210, bottom: 28, left: 150 }
      const height = rows.length * 28 + m.top + m.bottom
      const { sel, width } = frame(zoneSvg.value, height)
      sectorKey(sel, width, m.left)
      const x = d3.scaleLinear().domain([0, 1]).range([m.left, width - m.right])
      const y = d3.scaleBand().domain(rows.map((r) => r.name))
        .range([m.top, height - m.bottom]).padding(0.24)

      const bands = []
      rows.forEach((row) => {
        let acc = 0
        SECTORS.forEach((s) => {
          const share = row.shares[s.key] || 0
          if (share <= 0) {
            return
          }
          bands.push({ row, sector: s, share, from: acc })
          acc += share
        })
      })

      hoverable(
        sel.append('g').selectAll('rect').data(bands).join('rect')
          .attr('x', (d) => x(d.from)).attr('y', (d) => y(d.row.name))
          .attr('width', (d) => Math.max(0, x(d.from + d.share) - x(d.from)))
          .attr('height', y.bandwidth())
          .attr('fill', (d) => colour(d.sector.key)),
        (d) => ({
          title: `${d.row.name} · ${d.sector.label}`,
          lines: [
            `${(d.share * 100).toFixed(1)}% of its sector postings`,
            `${d.row.total.toLocaleString()} postings in the region`,
            `leading sector: ${d.row.z.label}`
          ]
        }))

      hoverable(
        sel.append('g').selectAll('text').data(rows).join('text')
          .attr('x', width - m.right + 10)
          .attr('y', (r) => y(r.name) + y.bandwidth() / 2 + 4)
          .attr('class', 'val')
          .text((r) => `${r.z.label} +${(r.z.margin * 100).toFixed(0)}`),
        (r) => ({
          title: `${r.name} reads as ${r.z.label}`,
          lines: [
            `${(r.z.share * 100).toFixed(1)}% of its sector postings`,
            `${(r.z.margin * 100).toFixed(1)} points ahead of the next sector`,
            r.z.margin < 0.05
              ? 'a narrow lead: this region has a mix, not a character'
              : 'a clear lead'
          ]
        }))
      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y))
      sel.append('g').attr('transform', `translate(0,${height - m.bottom})`)
        .call(d3.axisBottom(x).ticks(5).tickFormat(d3.format('.0%')))
    }

    function drawTrends(buckets) {
      if (!trendSvg.value || buckets.length < 3) {
        return
      }
      // Share of the month, not the count. Collection wound down across this
      // corpus -- postings per month fall about 7% a month -- so every
      // sector's raw count falls with it and every sparkline slopes down.
      // That is the scraper stopping, not the job market turning.
      const series = SECTORS.map((s) => ({
        key: s.key,
        label: s.label,
        values: shareSeries(buckets, s.key)
      })).filter((s) => d3.sum(s.values) > 0)
      if (!series.length) {
        return
      }
      const cols = 3
      const rows = Math.ceil(series.length / cols)
      const cellH = 104
      const { sel, width, height } = frame(trendSvg.value, rows * cellH + 24)
      const cellW = width / cols

      series.forEach((s, i) => {
        const { fit, projected } = project(s.values, PROJECT_MONTHS)
        const all = s.values.concat(projected)
        const gx = (i % cols) * cellW
        const gy = Math.floor(i / cols) * cellH
        const g = sel.append('g').attr('transform', `translate(${gx},${gy})`)
        const x = d3.scaleLinear().domain([0, all.length - 1])
          .range([10, cellW - 18])
        const y = d3.scaleLinear().domain([0, d3.max(all) || 1])
          .range([cellH - 16, 34])
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

        g.append('rect').attr('x', 0).attr('y', 20).attr('width', 11)
          .attr('height', 11).attr('rx', 2).attr('fill', colour(s.key))
        g.append('text').attr('x', 16).attr('y', 30)
          .attr('class', 'small').text(s.label)
        const trend = growthRate(s.values)
        g.append('text').attr('x', 16).attr('y', 14)
          .attr('class', 'tiny')
          .text(`${trend >= 0 ? '+' : ''}${(trend * 100).toFixed(1)}%/mo`
            + ` · R² ${fit.r2.toFixed(2)}`)

        // A point per month, so a reader can put a number on any part of the
        // line rather than only see its direction.
        const marks = s.values.map((v, k) => ({ k, v, s, fit, trend }))
        hoverable(
          g.append('g').selectAll('circle').data(marks).join('circle')
            .attr('cx', (d) => x(d.k)).attr('cy', (d) => y(d.v))
            .attr('r', 7).attr('fill', 'transparent'),
          (d) => ({
            title: `${d.s.label} · ${monthLabel(buckets[d.k].val)}`,
            lines: [
              `${(d.v * 100).toFixed(2)}% of that month's postings`,
              `${((buckets[d.k][d.s.key] || {}).count || 0).toLocaleString()}`
                + ` of ${buckets[d.k].count.toLocaleString()}`,
              `trend ${d.trend >= 0 ? '+' : ''}`
                + `${(d.trend * 100).toFixed(1)}% a month, R² `
                + `${d.fit.r2.toFixed(2)}`
            ]
          }))
      })
    }

    function drawGaps(regions, buckets, national) {
      if (!gapSvg.value || !regions.length || buckets.length < 3) {
        return
      }
      // On share of the month, for the same reason the trends are. Measured
      // on raw counts every sector had negative growth -- collection winding
      // down, not hiring -- so nothing anywhere qualified as an opening and
      // this panel drew nothing at all, which read as a bug rather than as
      // an answer.
      const growth = {}
      SECTORS.forEach((s) => {
        growth[s.key] = growthRate(shareSeries(buckets, s.key))
      })
      const found = opportunities(regions, national, growth)
      const names = regions
        .filter((r) => r.total >= MIN_REGION_POSTINGS)
        .map((r) => r.name)

      if (!found.length || !names.length) {
        // Said rather than left blank. An empty panel is indistinguishable
        // from a broken one.
        const { sel, width } = frame(gapSvg.value, 76)
        sel.append('text').attr('x', 8).attr('y', 26).attr('class', 'small')
          .text('No openings found.')
        sel.append('text').attr('x', 8).attr('y', 46).attr('class', 'tiny')
          .text(names.length
            ? 'Every sector that is growing is already well represented in '
              + 'each of these regions.'
            : `No region has the ${MIN_REGION_POSTINGS.toLocaleString()} `
              + 'postings needed to read a shortfall from.')
        sel.attr('width', width)
        return
      }

      const m = { top: 88, right: 16, bottom: 16, left: 150 }
      const height = names.length * 26 + m.top + m.bottom
      const { sel, width } = frame(gapSvg.value, height)
      const x = d3.scaleBand().domain(SECTORS.map((s) => s.key))
        .range([m.left, width - m.right]).padding(0.06)
      const y = d3.scaleBand().domain(names)
        .range([m.top, height - m.bottom]).padding(0.06)
      const top = d3.max(found, (o) => o.score) || 1
      const shade = d3.scaleSequential(d3.interpolateYlGnBu).domain([0, top])

      const index = {}
      found.forEach((o) => { index[`${o.region}|${o.sector}`] = o })

      const cells = []
      names.forEach((name) => {
        SECTORS.forEach((s) => {
          cells.push({ name, sector: s, hit: index[`${name}|${s.key}`] })
        })
      })

      hoverable(
        sel.append('g').selectAll('rect').data(cells).join('rect')
          .attr('x', (c) => x(c.sector.key)).attr('y', (c) => y(c.name))
          .attr('width', x.bandwidth()).attr('height', y.bandwidth())
          .attr('fill', (c) => (c.hit ? shade(c.hit.score) : '#f1f3f5'))
          .attr('stroke', '#fff').attr('stroke-width', 1),
        (c) => ({
          title: `${c.name} · ${c.sector.label}`,
          lines: c.hit
            ? [
              `here ${(c.hit.local * 100).toFixed(1)}%, `
                + `everywhere ${(c.hit.national * 100).toFixed(1)}%`,
              `shortfall ${(c.hit.gap * 100).toFixed(1)} points`,
              `sector trend +${(c.hit.growth * 100).toFixed(1)}% a month`,
              `score ${(c.hit.score * 1000).toFixed(2)}`
            ]
            : [growth[c.sector.key] > 0
              ? 'already well represented here'
              : 'this sector is not growing across the corpus']
        }))

      sel.append('g').attr('transform', `translate(${m.left},0)`)
        .call(d3.axisLeft(y))
      sel.append('g').attr('transform', `translate(0,${m.top})`)
        .call(d3.axisTop(x).tickFormat((k) => {
          const s = SECTORS.find((c) => c.key === k)
          return s ? s.label : k
        }))
        .selectAll('text')
        .attr('transform', 'rotate(-32)')
        .style('text-anchor', 'start')

      // The colour ramp, so a dark cell can be read as a number.
      const rampW = 120
      const rampX = width - m.right - rampW
      const ramp = sel.append('g').attr('transform', `translate(${rampX},8)`)
      const id = 'gapramp'
      const grad = ramp.append('defs').append('linearGradient').attr('id', id)
      d3.range(0, 1.01, 0.1).forEach((t) => {
        grad.append('stop').attr('offset', `${t * 100}%`)
          .attr('stop-color', shade(t * top))
      })
      ramp.append('rect').attr('width', rampW).attr('height', 9).attr('rx', 2)
        .attr('fill', `url(#${id})`)
      ramp.append('text').attr('x', 0).attr('y', 22).attr('class', 'tiny')
        .text('no opening')
      ramp.append('text').attr('x', rampW).attr('y', 22).attr('class', 'tiny')
        .attr('text-anchor', 'end').text('strongest')
    }

    onMounted(() => {
      load()
      if (typeof ResizeObserver !== 'undefined') {
        // Redraw, never reload: the charts are a function of the data and
        // the width, and re-asking Solr on every resize step would issue a
        // six second query per frame of a window drag.
        //
        // On width alone, because drawing changes the height of what is being
        // observed: redrawing on any size change is a loop that the browser
        // eventually breaks with "ResizeObserver loop completed with
        // undelivered notifications". Redrawing at a width already drawn at
        // produces the same charts, so the guard also makes it free.
        observer = new ResizeObserver((entries) => {
          const width = Math.round(entries[0].contentRect.width)
          if (loading.value || width === drawnAt) {
            return
          }
          redraw()
        })
        observer.observe(root.value || document.body)
      }
    })
    onUnmounted(() => {
      if (observer) {
        observer.disconnect()
      }
    })

    return {
      root, hoursSvg, lifeSvg, zoneSvg, trendSvg, gapSvg, tip, jobLabel,
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
.analytics { position: relative; }
.tip { position: absolute; z-index: 20; pointer-events: none;
       background: #1f2933; color: #f5f7fa; border-radius: 4px;
       padding: 7px 9px; font-size: 0.78rem; line-height: 1.35;
       box-shadow: 0 3px 12px rgba(0,0,0,0.22); max-width: 300px;
       display: flex; flex-direction: column; gap: 1px; }
.tip strong { font-size: 0.82rem; }
.tip span { color: #c6d0da; }
.banner { background: #fdecea; border: 1px solid #f5c2bd; border-radius: 4px;
          padding: 8px 10px; }
:deep(.leg), :deep(.val) { font-size: 11px; fill: #3d464f; }
:deep(.small) { font-size: 11px; fill: #3d464f; font-weight: 600; }
:deep(.tiny) { font-size: 10px; fill: #8a949d; }
</style>
