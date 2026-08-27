<template>
  <section class="bar">
    <label class="path">
      Path to TSV files
      <input
        v-model="path"
        type="text"
        placeholder="/path/to/untranslated"
        :disabled="busy"
        @keyup.enter="runTranslate"
      />
    </label>
    <label class="exclude">
      Exclude
      <input
        v-model="exclude"
        type="text"
        placeholder=".git"
        :disabled="busy"
      />
    </label>
    <div class="actions">
      <button class="primary" :disabled="busy || !path.trim()" @click="runTranslate">
        Translate
      </button>
      <button class="ghost" :disabled="busy" @click="runReset">Reset</button>
      <span class="pill" :class="statusClass">{{ status || 'IDLE' }}</span>
    </div>
    <p v-if="notice" class="notice">{{ notice }}</p>
  </section>
</template>

<script>
import { computed, ref } from 'vue'
import { reset, translate } from '../api.js'

export default {
  name: 'ControlBar',
  props: {
    busy: { type: Boolean, default: false },
    status: { type: String, default: 'IDLE' },
    message: { type: String, default: '' }
  },
  emits: ['translated', 'reset'],
  setup(props, { emit }) {
    const path = ref('')
    const exclude = ref('')
    const notice = ref('')

    const statusClass = computed(() => (props.status || 'IDLE').toLowerCase())

    async function runTranslate() {
      notice.value = ''
      try {
        await translate(path.value.trim(), exclude.value.trim())
        emit('translated')
      } catch (e) {
        notice.value = e.message || String(e)
      }
    }

    async function runReset() {
      if (!window.confirm('Reset will wipe Solr, File Manager products, archive and jobs. The translation cache is kept. Continue?')) {
        return
      }
      notice.value = ''
      try {
        await reset()
        emit('reset')
      } catch (e) {
        notice.value = e.message || String(e)
      }
    }

    return { path, exclude, notice, statusClass, runTranslate, runReset }
  }
}
</script>

<style scoped>
.bar {
  display: grid;
  grid-template-columns: 1fr 8rem auto;
  gap: 0.75rem 1rem;
  align-items: end;
  padding: 1.1rem 0;
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.notice {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--cardinal);
  font-family: "Source Sans 3", "Segoe UI", Helvetica, Arial, sans-serif;
}

@media (max-width: 800px) {
  .bar {
    grid-template-columns: 1fr;
  }
}
</style>
