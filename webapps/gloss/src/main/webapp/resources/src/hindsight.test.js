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
import { CHECKS, SOURCES, VERDICTS, citations, tally, verdictLine }
  from './hindsight.js'

test('every check cites something, or says why it cannot be checked', () => {
  CHECKS.forEach((c) => {
    if (c.verdict === 'untestable') {
      assert.equal(c.sources.length, 0,
        c.key + ' is untestable but cites sources')
      return
    }
    assert.ok(c.sources.length > 0, c.key + ' has no source')
    assert.equal(citations(c).length, c.sources.length,
      c.key + ' cites a source that is not in SOURCES')
  })
})

test('every source has a label and a url', () => {
  Object.entries(SOURCES).forEach(([key, s]) => {
    assert.ok(s.label, key + ' has no label')
    assert.match(s.url, /^https:\/\//, key + ' is not an https url')
  })
})

test('every verdict is one the panel can draw', () => {
  CHECKS.forEach((c) => {
    assert.ok(VERDICTS[c.verdict], c.key + ' has verdict ' + c.verdict)
  })
})

test('the table is not a list of successes', () => {
  // A hindsight panel that only records hits is marketing. The misses are
  // the entries worth having, and their absence would mean nobody looked.
  const counts = tally(CHECKS)
  assert.ok(counts.missed > 0,
    'no check missed, which is not a believable result for a linear '
    + 'projection across a currency crisis')
})

test('the summary is written from the counts, not chosen', () => {
  assert.equal(
    verdictLine({ held: 2, partial: 2, missed: 2, untestable: 1 }),
    '2 of 6 checks held up, 2 partly, 2 missed. 1 cannot be checked.')
  assert.equal(
    verdictLine({ held: 0, partial: 0, missed: 5, untestable: 0 }),
    '0 of 5 checks held up, 0 partly, 5 missed. 0 cannot be checked.')
})

test('nothing to check says so rather than claiming a score', () => {
  assert.match(verdictLine({ held: 0, partial: 0, missed: 0, untestable: 3 }),
    /Nothing here can be checked/)
})

test('each check names the question it is about', () => {
  CHECKS.forEach((c) => {
    assert.match(c.question, /^Q\d+$/, c.key + ' names no challenge question')
  })
})

test('each check says what the index claimed and what happened', () => {
  CHECKS.forEach((c) => {
    assert.ok(c.claim && c.claim.length > 20, c.key + ' has no claim')
    assert.ok(c.happened && c.happened.length > 40,
      c.key + ' does not say what actually happened')
  })
})

test('the claims are measured live rather than written down', () => {
  // A number copied into this file would go stale the moment the index is
  // rebuilt, and would then be a claim about nothing.
  CHECKS.forEach((c) => {
    assert.ok(c.measure && c.measure.kind, c.key + ' has nothing to measure')
  })
})
