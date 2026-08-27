<template>
  <section class="progress">
    <header>
      <h2>In progress</h2>
      <p>
        {{ progress.status || 'TRANSLATING' }}
        <span v-if="progress.path"> · {{ progress.path }}</span>
        <span v-if="progress.solrDocs != null"> · {{ progress.solrDocs }} in Solr</span>
        <span v-if="progress.jobDirs != null"> · {{ progress.jobDirs }} job dirs</span>
      </p>
    </header>
    <pre>{{ log || 'Waiting for log…' }}</pre>
  </section>
</template>

<script>
export default {
  name: 'ProgressPane',
  props: {
    log: { type: String, default: '' },
    progress: { type: Object, default: () => ({}) }
  }
}
</script>

<style scoped>
.progress {
  background: #1a1410;
  color: #fff8e7;
  border-radius: 4px;
  margin: 0.5rem 0 1rem;
  overflow: hidden;
}

header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.7rem 1rem 0.4rem;
  border-bottom: 1px solid #3a3028;
}

h2 {
  margin: 0;
  font-size: 0.85rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--gold);
}

header p {
  margin: 0;
  font-size: 0.85rem;
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
  color: #e6d9c2;
}

pre {
  margin: 0;
  padding: 0.8rem 1rem 1rem;
  max-height: 16rem;
  overflow: auto;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
}
</style>
