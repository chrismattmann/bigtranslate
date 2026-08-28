<template>
  <section class="record-card">
    <header>
      <button class="ghost" type="button" @click="$emit('back')">← Postings</button>
      <p class="id" v-if="payload.id">{{ payload.id }}</p>
    </header>

    <div v-if="loading" class="empty">Loading record…</div>
    <div v-else-if="payload.found === false" class="empty">
      No Solr document with that id.
    </div>
    <div v-else>
      <h2>{{ title || 'Posting' }}</h2>
      <dl>
        <div v-for="field in visibleFields" :key="field.name" class="row">
          <dt>{{ label(field.name) }}</dt>
          <dd>
            <a
              v-if="field.name === 'url' && field.value"
              :href="field.value"
              target="_blank"
              rel="noopener"
            >{{ field.value }}</a>
            <a
              v-else-if="isLineageField(field.name) && field.value"
              :href="opsuiHref(field.value)"
            >{{ field.value }}</a>
            <span v-else-if="field.name === 'postedDate' || field.name === 'firstSeenDate' || field.name === 'lastSeenDate'">
              {{ prettyDate(field.value) }}
            </span>
            <span v-else>{{ field.value || '—' }}</span>
          </dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<script>
import { computed } from 'vue'
import { isLineageField, opsuiProductUrl } from '../opsuiLinks.js'

const LABELS = {
  title: 'Title',
  company: 'Company',
  location: 'Location',
  department: 'Department',
  jobtype: 'Job type',
  salary: 'Salary',
  start: 'Start',
  duration: 'Duration',
  applications: 'How to apply',
  contactPerson: 'Contact',
  phoneNumber: 'Phone',
  faxNumber: 'Fax',
  postedDate: 'Posted',
  firstSeenDate: 'First seen',
  lastSeenDate: 'Last seen',
  latitude: 'Latitude',
  longitude: 'Longitude',
  url: 'Original URL',
  id: 'Solr id',
  InputFiles: 'Input files',
  SplitFilename: 'Parent split',
  TsvFile: 'Original TSV'
}

export default {
  name: 'RecordView',
  props: {
    payload: { type: Object, default: () => ({ found: true, fields: [], id: '' }) },
    loading: { type: Boolean, default: false }
  },
  emits: ['back'],
  setup(props) {
    const title = computed(() => {
      const fields = props.payload.fields || []
      const hit = fields.find((f) => f.name === 'title')
      return hit ? hit.value : ''
    })
    const visibleFields = computed(() => {
      return (props.payload.fields || []).filter((f) => f.name !== 'title')
    })
    function label(name) {
      return LABELS[name] || name
    }
    function prettyDate(value) {
      if (!value) {
        return '—'
      }
      return String(value).replace('T00:00:00Z', '').replace('T00:00:00.000Z', '')
    }
    function opsuiHref(value) {
      return opsuiProductUrl(window.location.origin, value)
    }
    return { title, visibleFields, label, prettyDate, isLineageField, opsuiHref }
  }
}
</script>

<style scoped>
.record-card {
  background: var(--paper);
  border: 1px solid var(--line);
  margin-top: 0.75rem;
  padding: 0.9rem 1.1rem 1.4rem;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.6rem;
}

.id {
  margin: 0;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 0.75rem;
  color: var(--muted);
  word-break: break-all;
}

h2 {
  margin: 0 0 0.9rem;
  font-size: 1.35rem;
  color: var(--cardinal);
}

dl {
  margin: 0;
  display: grid;
  grid-template-columns: 11rem 1fr;
  gap: 0;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

.row {
  display: contents;
}

dt, dd {
  margin: 0;
  padding: 0.55rem 0.4rem;
  border-top: 1px solid var(--line);
  vertical-align: top;
}

dt {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

dd {
  font-size: 0.95rem;
  word-break: break-word;
}

dd a {
  color: var(--cardinal);
}

.empty {
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  padding: 1.2rem 0;
}

@media (max-width: 700px) {
  dl {
    grid-template-columns: 1fr;
  }
  dt {
    padding-bottom: 0;
    border-top: 1px solid var(--line);
  }
  dd {
    border-top: 0;
    padding-top: 0.15rem;
  }
}
</style>
