<template>
  <section class="map-card">
    <header>
      <h2>Postings by location</h2>
      <p v-if="payload.solrDocs">
        {{ payload.solrDocs.toLocaleString() }} documents
        · {{ (payload.bubbles || []).length }} located
        <span v-if="payload.unlocated"> · {{ payload.unlocated.toLocaleString() }} without coordinates</span>
      </p>
      <p v-else>No postings in Solr yet. Translate a TSV directory, or wait for a run to land.</p>
    </header>
    <div ref="frame" class="frame">
      <svg ref="svg"></svg>
      <div v-if="tooltip" class="tip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
        <strong>{{ tooltip.location }}</strong>
        <span>{{ tooltip.count.toLocaleString() }} postings</span>
        <em>{{ tooltip.source === 'solr' ? 'lat/lng from the index' : 'geocoded from location' }}</em>
      </div>
    </div>
  </section>
</template>

<script>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as d3 from 'd3'
import { feature } from 'topojson-client'

export default {
  name: 'PostingMap',
  props: {
    payload: { type: Object, default: () => ({ bubbles: [] }) }
  },
  setup(props) {
    const svg = ref(null)
    const frame = ref(null)
    const tooltip = ref(null)
    let world = null
    let resizeObserver = null

    async function loadWorld() {
      if (world) {
        return world
      }
      const response = await fetch(`${import.meta.env.BASE_URL}countries-110m.json`)
      const topo = await response.json()
      world = feature(topo, topo.objects.countries)
      return world
    }

    function draw() {
      const node = svg.value
      const host = frame.value
      if (!node || !host) {
        return
      }
      const width = host.clientWidth || 900
      const height = Math.max(360, Math.round(width * 0.52))
      const bubbles = props.payload.bubbles || []
      const projection = d3.geoNaturalEarth1().fitExtent(
        [[12, 12], [width - 12, height - 12]],
        { type: 'Sphere' }
      )
      const path = d3.geoPath(projection)
      const maxCount = d3.max(bubbles, (d) => d.count) || 1
      const radius = d3.scaleSqrt().domain([0, maxCount]).range([0, Math.min(48, width / 18)])

      const sel = d3.select(node)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('width', width)
        .attr('height', height)

      sel.selectAll('*').remove()

      sel.append('path')
        .datum({ type: 'Sphere' })
        .attr('d', path)
        .attr('fill', '#fffdf6')
        .attr('stroke', '#e6d9c2')

      if (world) {
        sel.append('g')
          .selectAll('path')
          .data(world.features)
          .join('path')
          .attr('d', path)
          .attr('fill', '#f3e6cc')
          .attr('stroke', '#d7c4a3')
          .attr('stroke-width', 0.4)
      }

      const g = sel.append('g')
      g.selectAll('circle')
        .data(bubbles.slice().sort((a, b) => b.count - a.count))
        .join('circle')
        .attr('cx', (d) => projection([d.lng, d.lat])[0])
        .attr('cy', (d) => projection([d.lng, d.lat])[1])
        .attr('r', (d) => radius(d.count))
        .attr('fill', '#990000')
        .attr('fill-opacity', 0.45)
        .attr('stroke', '#ffcc00')
        .attr('stroke-width', 1.2)
        .on('mousemove', (event, d) => {
          const rect = host.getBoundingClientRect()
          tooltip.value = {
            location: d.location,
            count: d.count,
            source: d.source,
            x: event.clientX - rect.left + 12,
            y: event.clientY - rect.top + 12
          }
        })
        .on('mouseleave', () => {
          tooltip.value = null
        })
    }

    async function redraw() {
      try {
        await loadWorld()
      } catch (e) {
        world = null
      }
      draw()
    }

    onMounted(() => {
      redraw()
      if (typeof ResizeObserver !== 'undefined' && frame.value) {
        resizeObserver = new ResizeObserver(() => draw())
        resizeObserver.observe(frame.value)
      }
    })

    onUnmounted(() => {
      if (resizeObserver) {
        resizeObserver.disconnect()
      }
    })

    watch(() => props.payload, () => redraw(), { deep: true })

    return { svg, frame, tooltip }
  }
}
</script>

<style scoped>
.map-card {
  background: var(--paper);
  border: 1px solid var(--line);
  margin-top: 0.75rem;
}

header {
  padding: 0.9rem 1rem 0.4rem;
}

h2 {
  margin: 0;
  font-size: 1.15rem;
  color: var(--cardinal);
}

header p {
  margin: 0.2rem 0 0;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.9rem;
}

.frame {
  position: relative;
  width: 100%;
}

svg {
  display: block;
  width: 100%;
  height: auto;
}

.tip {
  position: absolute;
  background: #1a1410;
  color: #fff8e7;
  padding: 0.45rem 0.6rem;
  border-radius: 4px;
  pointer-events: none;
  min-width: 10rem;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.82rem;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}

.tip strong, .tip span, .tip em {
  display: block;
}

.tip em {
  font-style: normal;
  color: var(--gold);
  font-size: 0.72rem;
  margin-top: 0.15rem;
}
</style>
