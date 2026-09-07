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
