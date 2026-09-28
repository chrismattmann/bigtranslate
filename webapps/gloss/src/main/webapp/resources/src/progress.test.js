// Licensed to the Apache Software Foundation (ASF) under one or more
// contributor license agreements.  See the NOTICE file distributed with
// this work for additional information regarding copyright ownership.
// The ASF licenses this file to You under the Apache License, Version 2.0
// (the "License"); you may not use this file except in compliance with
// the License.  You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  measure,
  percent, rateLabel, remainingLabel, elapsedLabel, stageLabel, duration
} from './progress.js'

const NOW = 1788800000000
const minutesAgo = (m) => NOW - m * 60000

test('reports how far along the run is', () => {
  assert.equal(percent({ chunksTotal: 458, chunksDone: 378 }), 83)
  assert.equal(percent({ chunksTotal: 0, chunksDone: 0 }), 0)
  assert.equal(percent({}), 0)
})

test('estimates what is left from the rate it has managed', () => {
  // The state of the real run: 378 of 458 after 686 minutes of
  // translating. Eighty left at that rate is about two and a half hours.
  const progress = {
    chunksTotal: 458, chunksDone: 378, translatingSince: minutesAgo(686)
  }
  assert.match(remainingLabel(progress, NOW), /^about 2h/)
  assert.match(rateLabel(progress, NOW), /chunks\/hour$/)
})

test('measures the rate from the first chunk, not the start of the run', () => {
  // Ten minutes of the run were the extract pass, translating nothing.
  // Counting those would put the rate a fifth too low and the estimate a
  // quarter too high.
  const progress = {
    chunksTotal: 100, chunksDone: 50,
    startedAt: minutesAgo(60), translatingSince: minutesAgo(50)
  }
  assert.equal(remainingLabel(progress, NOW), 'about 50m')
})

test('says nothing rather than guessing before the first chunk', () => {
  const progress = { chunksTotal: 458, chunksDone: 0, startedAt: minutesAgo(5) }
  assert.equal(rateLabel(progress, NOW), '')
  assert.equal(remainingLabel(progress, NOW), '')
})

test('says nothing about what is left once it is done', () => {
  const progress = {
    chunksTotal: 458, chunksDone: 458, translatingSince: minutesAgo(600)
  }
  assert.equal(remainingLabel(progress, NOW), '')
})

test('names the stage rather than repeating a status', () => {
  assert.equal(stageLabel({ stage: 'extracting' }), 'Reading the corpus')
  assert.equal(stageLabel({ stage: 'translating' }), 'Translating')
  assert.equal(stageLabel({ stage: 'joining' }), 'Indexing')
  assert.equal(stageLabel({ status: 'RESETTING' }), 'RESETTING')
})

test('reads durations the way a person would say them', () => {
  assert.equal(duration(90), '2m')
  assert.equal(duration(3600), '1h')
  assert.equal(duration(8760), '2h 26m')
  assert.equal(duration(5), '1m')
})

test('elapsed falls back to the start when nothing has translated yet', () => {
  assert.equal(elapsedLabel({ startedAt: minutesAgo(30) }, NOW), '30m')
  assert.equal(elapsedLabel({}, NOW), '')
})

test('the log pane is bounded and scrolls inside itself', () => {
  // Not arithmetic, but worth pinning: unbounded, the pane printed a whole
  // log down the page. One run showed ninety lines of a translation from
  // two days earlier and pushed everything else off the screen.
  const pane = readFileSync(
    new URL('./components/ProgressPane.vue', import.meta.url), 'utf8')
  assert.match(pane, /max-height/, 'the log pane is unbounded')
  assert.match(pane, /overflow:\s*auto/, 'the log pane does not scroll')
})

test('the join draws files, because its chunk counts are already full', () => {
  // Solr holds every document uncommitted until the commit at the very
  // end, so the index reads as empty for an hour and a half. The chunk
  // counts by then are 458 of 458, so drawing them left the bar full
  // while the index was still being built -- finished, or hung.
  const joining = {
    stage: 'joining',
    chunksDone: 458,
    chunksTotal: 458,
    filesDone: 1931,
    filesTotal: 2806
  }
  assert.deepEqual(measure(joining), { done: 1931, total: 2806, unit: 'files' })
})

test('the join falls back to chunks until the shards have reported', () => {
  const joining = { stage: 'joining', chunksDone: 458, chunksTotal: 458 }
  assert.equal(measure(joining).unit, 'chunks')
})

test('translating still draws chunks', () => {
  const translating = {
    stage: 'translating',
    chunksDone: 197,
    chunksTotal: 458,
    filesDone: 2806,
    filesTotal: 2806
  }
  assert.deepEqual(measure(translating),
    { done: 197, total: 458, unit: 'chunks' })
})

// The join's banner said 100% while its bar said 25%, from the same marker.
//
// measure() had been taught that the join counts files; percent() had not, and
// never reached it -- it returned the weighted fraction whenever weightTotal
// was set, and the weights are the translation work, complete the moment the
// last chunk is translated. So for the whole of the join the two numbers on one
// screen disagreed, and the one in the banner said the run had finished.
const JOINING = {
  stage: 'joining',
  chunksDone: 458,
  chunksTotal: 458,
  weightDone: 102513038,
  weightTotal: 102513038,
  filesDone: 690,
  filesTotal: 2806,
  translatingSince: minutesAgo(1200)
}

test('the banner measures the stage it is in, not the one before', () => {
  assert.equal(percent(JOINING), 25)
  // The number the bar shows, from the same marker, so they cannot disagree.
  const { done, total } = measure(JOINING)
  assert.equal(percent(JOINING), Math.round((done / total) * 100))
})

test('the weights still drive the translating stage', () => {
  // Which is the reason they exist: chunks hold equal counts and unequal work.
  assert.equal(percent({
    stage: 'translating',
    chunksDone: 229,
    chunksTotal: 458,
    weightDone: 25628259,
    weightTotal: 102513038
  }), 25)
})

test('the extract measures files too, not a weight it has not earned', () => {
  assert.equal(percent({
    stage: 'extracting', filesDone: 1403, filesTotal: 2806,
    chunksDone: 0, chunksTotal: 0, weightTotal: 0
  }), 50)
})

test('no stale chunk rate is shown once chunks have stopped moving', () => {
  // chunksDone sits at its final value while translatingSince recedes, so this
  // reported the average over a translation that had already finished -- 23
  // chunks/hour, offered as the rate of the join on screen.
  assert.equal(rateLabel(JOINING, NOW), '')
  assert.equal(remainingLabel(JOINING, NOW), '')
})

test('the translating stage still reports its rate', () => {
  assert.equal(rateLabel({
    stage: 'translating', chunksDone: 60, chunksTotal: 458,
    translatingSince: minutesAgo(60)
  }, NOW), '1.0 chunks/min')
})
