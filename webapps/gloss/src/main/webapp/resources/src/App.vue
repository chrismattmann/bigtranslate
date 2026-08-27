<template>
  <div class="shell">
    <header class="mast">
      <div class="brand">
        <svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
          <circle cx="16" cy="16" r="12" fill="none" stroke="currentColor" stroke-width="2"/>
          <ellipse cx="16" cy="16" rx="5" ry="12" fill="none" stroke="currentColor" stroke-width="1.5"/>
          <line x1="4" y1="16" x2="28" y2="16" stroke="currentColor" stroke-width="1.5"/>
        </svg>
        <div>
          <h1>Gloss</h1>
          <p>BigTranslate</p>
        </div>
      </div>
      <nav>
        <button :class="{ active: view === 'map' }" @click="go('map')">Map</button>
        <button :class="{ active: view === 'table' || view === 'record' }" @click="go('table')">Table</button>
        <button :class="{ active: view === 'facets' }" @click="go('facets')">Facets</button>
      </nav>
    </header>

    <ControlBar
      :busy="busy"
      :status="status"
      :message="message"
      @translated="onChanged"
      @reset="onChanged"
    />

    <SummaryBar :summary="summary" :oodt="oodt" />

    <ProgressPane v-if="busy" :log="log" :progress="progress" />

    <PostingMap v-if="view === 'map'" :payload="mapPayload" />
    <PostingTable
      v-else-if="view === 'table'"
      :payload="tablePayload"
      :query="query"
      :filters="filters"
      :page="page"
      :sort="sort"
      :dir="dir"
      @search="onSearch"
      @page="onPage"
      @sort="onSort"
      @open="openRecord"
      @remove-filter="removeFilter"
      @clear-filters="clearFilters"
    />
    <RecordView
      v-else-if="view === 'record'"
      :payload="recordPayload"
      :loading="recordLoading"
      @back="go('table')"
    />
    <FacetPanel
      v-else
      :payload="facetPayload"
      :filters="filters"
      @toggle-filter="toggleFilter"
      @remove-filter="removeFilter"
      @clear-filters="clearFilters"
    />

    <p v-if="error" class="banner">{{ error }}</p>
  </div>
</template>

<script>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ControlBar from './components/ControlBar.vue'
import SummaryBar from './components/SummaryBar.vue'
import ProgressPane from './components/ProgressPane.vue'
import PostingMap from './components/PostingMap.vue'
import PostingTable from './components/PostingTable.vue'
import RecordView from './components/RecordView.vue'
import FacetPanel from './components/FacetPanel.vue'
import { getFacets, getLog, getMap, getOodtStatus, getProgress, getRecord, getStatus, getSummary, getTable } from './api.js'

export default {
  name: 'App',
  components: { ControlBar, SummaryBar, ProgressPane, PostingMap, PostingTable, FacetPanel, RecordView },
  setup() {
    const parsed = parseHash()
    const view = ref(parsed.view)
    const recordId = ref(parsed.id)
    const status = ref('IDLE')
    const message = ref('')
    const summary = ref({})
    const oodt = ref({})
    const mapPayload = ref({ bubbles: [], solrDocs: 0, unlocated: 0 })
    const tablePayload = ref({ docs: [], numFound: 0, start: 0, rows: 25 })
    const facetPayload = ref({ facets: [], numFound: 0 })
    const recordPayload = ref({ found: true, fields: [], id: '' })
    const recordLoading = ref(false)
    const query = ref('')
    const filters = ref([])
    const page = ref(0)
    const sort = ref('postedDate')
    const dir = ref('desc')
    const rows = 25
    const log = ref('')
    const progress = ref({})
    const error = ref('')
    let timer = null

    function parseHash() {
      const raw = (window.location.hash || '').replace(/^#/, '')
      if (raw.indexOf('record/') === 0) {
        try {
          return { view: 'record', id: decodeURIComponent(raw.slice('record/'.length)) }
        } catch (e) {
          return { view: 'table', id: '' }
        }
      }
      if (raw === 'table' || raw === 'facets' || raw === 'map') {
        return { view: raw, id: '' }
      }
      return { view: 'map', id: '' }
    }

    function go(next) {
      view.value = next
      if (next !== 'record') {
        recordId.value = ''
      }
    }

    const busy = computed(() =>
      status.value === 'TRANSLATING' || status.value === 'RESETTING')

    async function refresh() {
      try {
        const start = page.value * rows
        const [st, sum, health, mapped, table, facets] = await Promise.all([
          getStatus(),
          getSummary(),
          getOodtStatus(),
          getMap(),
          getTable(query.value, start, rows, filters.value, sort.value, dir.value),
          getFacets(query.value, filters.value)
        ])
        status.value = st.status || 'IDLE'
        message.value = st.message || ''
        summary.value = sum
        oodt.value = health
        mapPayload.value = mapped
        tablePayload.value = table
        facetPayload.value = facets
        if (st.status === 'TRANSLATING' || st.status === 'RESETTING') {
          const [prog, tail] = await Promise.all([getProgress(), getLog()])
          progress.value = prog
          log.value = tail
        }
        error.value = ''
      } catch (e) {
        error.value = e.message || String(e)
      }
    }

    async function loadRecord(id) {
      if (!id) {
        return
      }
      recordLoading.value = true
      try {
        recordPayload.value = await getRecord(id)
        error.value = ''
      } catch (e) {
        error.value = e.message || String(e)
      } finally {
        recordLoading.value = false
      }
    }

    function onChanged() {
      refresh()
    }

    function onSearch(q) {
      query.value = q
      page.value = 0
      refresh()
    }

    function onPage(next) {
      page.value = next
      refresh()
    }

    function onSort(field) {
      if (sort.value === field) {
        dir.value = dir.value === 'asc' ? 'desc' : 'asc'
      } else {
        sort.value = field
        dir.value = 'asc'
      }
      page.value = 0
      refresh()
    }

    function openRecord(id) {
      recordId.value = id
      view.value = 'record'
      loadRecord(id)
    }

    function sameFilter(a, b) {
      return a.field === b.field && a.value === b.value
    }

    function toggleFilter(next) {
      const exists = filters.value.some((f) => sameFilter(f, next))
      filters.value = exists
        ? filters.value.filter((f) => !sameFilter(f, next))
        : filters.value.concat([next])
      page.value = 0
      refresh()
    }

    function removeFilter(target) {
      filters.value = filters.value.filter((f) => !sameFilter(f, target))
      page.value = 0
      refresh()
    }

    function clearFilters() {
      filters.value = []
      page.value = 0
      refresh()
    }

    function writeHash() {
      const next = view.value === 'record' && recordId.value
        ? 'record/' + encodeURIComponent(recordId.value)
        : view.value
      if (window.location.hash.replace(/^#/, '') !== next) {
        window.location.hash = next
      }
    }

    watch([view, recordId], writeHash)

    onMounted(() => {
      window.addEventListener('hashchange', () => {
        const next = parseHash()
        view.value = next.view
        recordId.value = next.id
        if (next.view === 'record' && next.id) {
          loadRecord(next.id)
        }
      })
      if (view.value === 'record' && recordId.value) {
        loadRecord(recordId.value)
      }
      refresh()
      timer = setInterval(refresh, 4000)
    })

    onUnmounted(() => {
      if (timer) {
        clearInterval(timer)
      }
    })

    return {
      view, status, message, summary, oodt, mapPayload, tablePayload, facetPayload,
      recordPayload, recordLoading, query, filters, page, sort, dir, log, progress,
      error, busy, go, onChanged, onSearch, onPage, onSort, openRecord,
      toggleFilter, removeFilter, clearFilters
    }
  }
}
</script>

<style scoped>
.shell {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.25rem 3rem;
}

.mast {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.4rem 0 1rem;
  border-bottom: 3px solid var(--cardinal);
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  color: var(--cardinal);
}

.mark {
  width: 2.4rem;
  height: 2.4rem;
}

h1 {
  font-size: 2rem;
  line-height: 1;
  margin: 0;
  letter-spacing: 0.02em;
}

.brand p {
  margin: 0.15rem 0 0;
  font-size: 0.8rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

nav {
  display: flex;
  gap: 0.4rem;
}

nav button {
  background: transparent;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  border-radius: 0;
  padding: 0.35rem 0.6rem;
}

nav button.active {
  color: var(--cardinal);
  border-bottom-color: var(--gold);
}

.banner {
  background: #f7dede;
  color: var(--cardinal);
  padding: 0.75rem 1rem;
  border-radius: 4px;
}
</style>
