<template>
  <section class="table-card">
    <header>
      <div>
        <h2>Postings</h2>
        <p v-if="payload.numFound != null">
          {{ Number(payload.numFound).toLocaleString() }} matching
          <span v-if="query"> · “{{ query }}”</span>
        </p>
        <p v-else>No postings in Solr yet.</p>
      </div>
      <form class="search" @submit.prevent="emitSearch">
        <input
          v-model="draft"
          type="text"
          placeholder="Search titles, companies, locations…"
        />
        <button class="primary" type="submit">Search</button>
      </form>
    </header>

    <div v-if="filters.length" class="chips">
      <button
        v-for="(f, i) in filters"
        :key="f.field + f.value + i"
        class="chip"
        type="button"
        @click="$emit('remove-filter', f)"
      >
        {{ f.field }}: {{ f.value }} ×
      </button>
      <button class="chip clear" type="button" @click="$emit('clear-filters')">Clear</button>
    </div>

    <div class="scroller">
      <table>
        <thead>
          <tr>
            <th
              v-for="col in columns"
              :key="col.field"
              :class="{ sorted: sort === col.field }"
            >
              <button type="button" @click="$emit('sort', col.field)">
                {{ col.label }}
                <span class="arrow" v-if="sort === col.field">{{ dir === 'desc' ? '▼' : '▲' }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in payload.docs || []" :key="row.id || row.title">
            <td>
              <a v-if="row.id" href="#" @click.prevent="$emit('open', row.id)">{{ row.title || row.id }}</a>
              <span v-else>{{ row.title }}</span>
            </td>
            <td>{{ row.company }}</td>
            <td>{{ row.location }}</td>
            <td>{{ row.jobtype }}</td>
            <td>{{ row.salary }}</td>
            <td class="date">{{ prettyDate(row.postedDate) }}</td>
          </tr>
          <tr v-if="!(payload.docs && payload.docs.length)">
            <td colspan="6" class="empty">Nothing matches these filters.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="pages > 1">
      <button class="ghost" :disabled="page <= 0" @click="$emit('page', page - 1)">Previous</button>
      <span>Page {{ page + 1 }} of {{ pages }}</span>
      <button class="ghost" :disabled="page + 1 >= pages" @click="$emit('page', page + 1)">Next</button>
    </footer>
  </section>
</template>

<script>
import { computed, ref, watch } from 'vue'

export default {
  name: 'PostingTable',
  props: {
    payload: { type: Object, default: () => ({ docs: [], numFound: 0, rows: 25 }) },
    query: { type: String, default: '' },
    filters: { type: Array, default: () => [] },
    page: { type: Number, default: 0 },
    sort: { type: String, default: 'postedDate' },
    dir: { type: String, default: 'desc' }
  },
  emits: ['search', 'page', 'remove-filter', 'clear-filters', 'sort', 'open'],
  setup(props, { emit }) {
    const columns = [
      { field: 'title', label: 'Title' },
      { field: 'company', label: 'Company' },
      { field: 'location', label: 'Location' },
      { field: 'jobtype', label: 'Type' },
      { field: 'salary', label: 'Salary' },
      { field: 'postedDate', label: 'Time' }
    ]
    const draft = ref(props.query)
    watch(() => props.query, (q) => { draft.value = q })

    const pages = computed(() => {
      const rows = props.payload.rows || 25
      const found = props.payload.numFound || 0
      return Math.max(1, Math.ceil(found / rows))
    })

    function emitSearch() {
      emit('search', draft.value.trim())
    }

    function prettyDate(value) {
      if (!value) {
        return ''
      }
      return String(value).replace('T00:00:00Z', '').replace('T00:00:00.000Z', '')
    }

    return { draft, pages, columns, emitSearch, prettyDate }
  }
}
</script>

<style scoped>
.table-card {
  background: var(--paper);
  border: 1px solid var(--line);
  margin-top: 0.75rem;
}

header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-end;
  padding: 0.9rem 1rem 0.6rem;
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

.search {
  display: flex;
  gap: 0.4rem;
  min-width: 18rem;
}

.search input {
  flex: 1;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0 1rem 0.6rem;
}

.chip {
  background: #fff1c2;
  color: var(--ink);
  border: 1px solid var(--gold);
  border-radius: 999px;
  padding: 0.2rem 0.7rem;
  font-size: 0.78rem;
  font-weight: 600;
}

.chip.clear {
  background: transparent;
  color: var(--cardinal);
  border-color: var(--cardinal);
}

.scroller {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.88rem;
}

th, td {
  text-align: left;
  padding: 0.5rem 0.85rem;
  border-top: 1px solid var(--line);
  vertical-align: top;
}

th {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  background: #fffdf6;
  white-space: nowrap;
}

th button {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: inherit;
  font-weight: 700;
  letter-spacing: inherit;
  text-transform: inherit;
}

th.sorted button {
  color: var(--cardinal);
}

.arrow {
  color: var(--gold);
  margin-left: 0.2rem;
}

td a {
  color: var(--cardinal);
  text-decoration: none;
  font-weight: 600;
}

td a:hover {
  text-decoration: underline;
}

.date {
  white-space: nowrap;
  color: var(--muted);
}

.empty {
  text-align: center;
  color: var(--muted);
  padding: 1.4rem;
}

footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.7rem 1rem;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.85rem;
  color: var(--muted);
}

@media (max-width: 800px) {
  header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
