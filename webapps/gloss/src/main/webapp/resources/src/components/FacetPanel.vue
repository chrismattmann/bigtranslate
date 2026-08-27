<template>
  <section class="facet-card">
    <header>
      <h2>Facets</h2>
      <p v-if="payload.numFound != null">
        {{ Number(payload.numFound).toLocaleString() }} postings
        <span v-if="filters.length"> after {{ filters.length }} filter{{ filters.length === 1 ? '' : 's' }}</span>
      </p>
      <p v-else>No postings in Solr yet.</p>
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

    <div class="grid">
      <article v-for="group in payload.facets || []" :key="group.field">
        <h3>{{ label(group.field) }}</h3>
        <ul>
          <li v-for="item in (group.values || []).slice(0, 12)" :key="item.value">
            <button
              type="button"
              :class="{ on: selected(group.field, item.value) }"
              @click="$emit('toggle-filter', { field: group.field, value: item.value })"
            >
              <span class="name">{{ item.value }}</span>
              <span class="count">{{ Number(item.count).toLocaleString() }}</span>
            </button>
          </li>
          <li v-if="!(group.values && group.values.length)" class="empty">None</li>
        </ul>
      </article>
    </div>
  </section>
</template>

<script>
const LABELS = {
  location: 'Location',
  department: 'Department',
  jobtype: 'Job type',
  company: 'Company',
  salary: 'Salary',
  start: 'Start',
  duration: 'Duration',
  applications: 'How to apply'
}

export default {
  name: 'FacetPanel',
  props: {
    payload: { type: Object, default: () => ({ facets: [], numFound: 0 }) },
    filters: { type: Array, default: () => [] }
  },
  emits: ['toggle-filter', 'remove-filter', 'clear-filters'],
  setup(props) {
    function label(field) {
      return LABELS[field] || field
    }
    function selected(field, value) {
      return props.filters.some((f) => f.field === field && f.value === value)
    }
    return { label, selected }
  }
}
</script>

<style scoped>
.facet-card {
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

.grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  border-top: 1px solid var(--line);
}

article {
  padding: 0.75rem 0.9rem 1rem;
  border-right: 1px solid var(--line);
}

article:nth-child(4n) {
  border-right: 0;
}

h3 {
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

button {
  width: 100%;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  background: transparent;
  color: var(--ink);
  padding: 0.28rem 0.15rem;
  font-weight: 500;
  text-align: left;
  border-radius: 2px;
}

button.on {
  background: #fff1c2;
  color: var(--cardinal);
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.empty {
  color: var(--muted);
  font-size: 0.85rem;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  article:nth-child(4n) {
    border-right: 1px solid var(--line);
  }
  article:nth-child(2n) {
    border-right: 0;
  }
}
</style>
