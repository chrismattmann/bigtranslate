<template>
  <section class="cards">
    <article>
      <h3>Postings</h3>
      <p class="num">{{ format(summary.solrDocs) }}</p>
      <small>in Solr</small>
    </article>
    <article>
      <h3>Locations</h3>
      <p class="num">{{ format(summary.locations) }}</p>
      <small>on the map</small>
    </article>
    <article>
      <h3>Cache</h3>
      <p class="num">{{ format(summary.entries) }}</p>
      <small>translated strings</small>
    </article>
    <article>
      <h3>Glossary</h3>
      <p class="num">{{ format(summary.glossaryEntries) }}</p>
      <small>overrides</small>
    </article>
    <article class="health">
      <h3>Services</h3>
      <ul>
        <li><span class="dot" :class="oodt.fm ? 'on' : 'off'"></span> File Manager</li>
        <li><span class="dot" :class="oodt.wm ? 'on' : 'off'"></span> Workflow</li>
        <li><span class="dot" :class="oodt.rm ? 'on' : 'off'"></span> Resource</li>
        <li><span class="dot" :class="oodt.solr ? 'on' : 'off'"></span> Solr</li>
      </ul>
    </article>
  </section>
</template>

<script>
export default {
  name: 'SummaryBar',
  props: {
    summary: { type: Object, default: () => ({}) },
    oodt: { type: Object, default: () => ({}) }
  },
  setup() {
    function format(value) {
      if (value == null) {
        return '—'
      }
      return Number(value).toLocaleString()
    }
    return { format }
  }
}
</script>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
}

article {
  background: var(--paper);
  border: 1px solid var(--line);
  border-top: 4px solid var(--gold);
  padding: 0.8rem 0.9rem 0.9rem;
}

h3 {
  margin: 0;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

.num {
  margin: 0.25rem 0 0;
  font-size: 1.7rem;
  color: var(--cardinal);
}

small {
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

.health ul {
  list-style: none;
  margin: 0.4rem 0 0;
  padding: 0;
  font-size: 0.82rem;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

.health li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.15rem 0;
}

@media (max-width: 900px) {
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
