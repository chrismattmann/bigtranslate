<template>
  <section class="progress">
    <header>
      <h2>In progress</h2>
      <p>
        {{ stageLabel }}
        <!-- Who started it. A run begun from the command line is the ordinary
             case, and the back end says so; the panel used to drop that on the
             floor, leaving no way to tell it from one started here. -->
        <span v-if="progress.message" class="whose"> ({{ progress.message }})</span>
        <span v-if="progress.path"> · {{ progress.path }}</span>
      </p>
    </header>

    <!--
      What it has done, rather than only what it is doing. A status of
      TRANSLATING and a tail of the log says almost nothing at hour eleven
      of a run: the question is how far along it is and when it will end.
    -->
    <div v-if="hasCounts" class="tally">
      <div class="bar" role="progressbar" :aria-valuenow="percent"
           aria-valuemin="0" aria-valuemax="100">
        <span :style="{ width: percent + '%' }"></span>
      </div>
      <dl>
        <div><dt>Chunks</dt><dd>{{ progress.chunksDone }} of {{ progress.chunksTotal }}</dd></div>
        <div><dt>Done</dt><dd>{{ percent }}%</dd></div>
        <div v-if="rate"><dt>Rate</dt><dd>{{ rate }}</dd></div>
        <div v-if="elapsed"><dt>Elapsed</dt><dd>{{ elapsed }}</dd></div>
        <div v-if="remaining"><dt>Remaining</dt><dd>{{ remaining }}</dd></div>
        <div v-if="progress.solrDocs != null"><dt>In Solr</dt><dd>{{ solrDocs }}</dd></div>
      </dl>
    </div>

    <!--
      A run started from the command line writes to the deployment's own log,
      not to the one Gloss keeps of what it did itself, so this waited for a
      log that was never going to arrive and said "Waiting for log…" for the
      length of the run. The back end now hands over whichever log the run is
      actually writing; when there genuinely is not one yet, say that rather
      than implying something is stuck.
    -->
    <pre v-if="log" class="tail">{{ log }}</pre>
    <p v-else-if="!hasCounts" class="nolog">
      No log output yet. The workflow manager is running this; its progress
      shows above and in OPSUI.
    </p>
  </section>
</template>

<script>
// The arithmetic lives in progress.js, tested on its own: what a run has
// done and when it will end is the part worth being sure of, and it is
// awkward to check through a rendered component.
import {
  stageLabel, percent, rateLabel, remainingLabel, elapsedLabel
} from '../progress.js'

export default {
  name: 'ProgressPane',
  props: {
    log: { type: String, default: '' },
    progress: { type: Object, default: () => ({}) }
  },
  data () {
    // The estimate is a function of the clock as well as the counts, so it
    // is re-read on a timer; otherwise "about 2h" sits there unchanged
    // while the two hours pass.
    return { now: Date.now(), ticker: null }
  },
  mounted () {
    this.ticker = setInterval(() => { this.now = Date.now() }, 30000)
  },
  beforeUnmount () {
    if (this.ticker) clearInterval(this.ticker)
  },
  computed: {
    stageLabel () { return stageLabel(this.progress) },
    hasCounts () { return Number(this.progress.chunksTotal) > 0 },
    percent () { return percent(this.progress) },
    rate () { return rateLabel(this.progress, this.now) },
    elapsed () { return elapsedLabel(this.progress, this.now) },
    remaining () { return remainingLabel(this.progress, this.now) },
    solrDocs () { return Number(this.progress.solrDocs).toLocaleString() }
  }
}
</script>

<style scoped>
/*
 * Bounded, and scrolled inside itself. Unbounded it printed the whole log
 * down the page -- one run showed ninety lines of a translation from two
 * days earlier and pushed everything else off the screen.
 */
.tail {
  max-height: 18rem;
  overflow: auto;
  margin: 0.75rem 0 0;
  padding: 0.75rem 0.9rem;
  background: rgba(127, 127, 127, 0.08);
  border: 1px solid rgba(127, 127, 127, 0.22);
  border-radius: 2px;
  font-size: 0.78rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.tally { margin: 0.75rem 0; }
.bar {
  height: 6px;
  background: rgba(127, 127, 127, 0.25);
  border-radius: 3px;
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: currentColor;
  transition: width 0.4s ease;
}
dl {
  display: flex;
  flex-wrap: wrap;
  gap: 0 1.5rem;
  margin: 0.6rem 0 0;
}
dl div { display: flex; gap: 0.35rem; align-items: baseline; }
dt { opacity: 0.65; font-size: 0.85em; }
dd { margin: 0; font-variant-numeric: tabular-nums; }
</style>
