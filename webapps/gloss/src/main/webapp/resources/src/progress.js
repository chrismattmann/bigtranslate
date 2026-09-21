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
//
// How far along a run is, and when it will end.
//
// Kept apart from the panel that shows it because the arithmetic is the
// part worth being sure of: a status of TRANSLATING and a tail of the log
// answers neither question anybody has at hour eleven of a fourteen hour
// run.

export const STAGES = {
  extracting: 'Reading the corpus',
  translating: 'Translating',
  joining: 'Indexing'
}

export function stageLabel (progress) {
  return STAGES[progress.stage] || progress.status || 'TRANSLATING'
}

// What the bar measures, which is not the same thing at every stage.
//
// Reading the corpus produces no chunk until it has finished, so a bar keyed
// to chunks sits at zero for the longest stage of the run and the pane falls
// back to showing log text. While the read is running the files it has got
// through are the progress, and the extract reports them.
export function measure (progress) {
  if (progress.stage === 'extracting' && Number(progress.filesTotal) > 0) {
    return {
      done: Number(progress.filesDone) || 0,
      total: Number(progress.filesTotal),
      unit: 'files'
    }
  }
  return {
    done: Number(progress.chunksDone) || 0,
    total: Number(progress.chunksTotal) || 0,
    unit: 'chunks'
  }
}

// How much of the work is done, which is not the same as how many chunks
// are ticked off.
//
// The extract sorts every distinct string by length before cutting chunks,
// so they hold equal counts and wildly unequal work: the first averages
// four characters a string, the last 254. Chunks happen to finish evenly
// across that range -- the scheduler dispatches them as nodes free up, not
// in order -- so counting them lands close to the truth by luck rather
// than by construction. It stops being luck the moment anything makes
// completion uneven: one slow node holding the long chunks, a resumed run
// picking up where it left off, a node joining late.
//
// So when the weights are there, they are used.
export function percent (progress) {
  const weighted = Number(progress.weightTotal)
  if (weighted > 0) {
    const done = Number(progress.weightDone) || 0
    return Math.min(100, Math.round((done / weighted) * 100))
  }
  const { done, total } = measure(progress)
  if (!total) return 0
  return Math.min(100, Math.round((done / total) * 100))
}

// Measured from the first chunk, not from the start of the run: the
// extract pass is ten minutes of apparently translating nothing on the
// full corpus, and folding it in makes every early estimate wrong.
export function chunksPerMinute (progress, now = Date.now()) {
  const since = Number(progress.translatingSince)
  const done = Number(progress.chunksDone)
  if (!since || !done) return 0
  const minutes = (now - since) / 60000
  return minutes > 0 ? done / minutes : 0
}

export function duration (seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  if (hours && minutes) return hours + 'h ' + minutes + 'm'
  if (hours) return hours + 'h'
  return Math.max(1, minutes) + 'm'
}

export function rateLabel (progress, now = Date.now()) {
  const perMinute = chunksPerMinute(progress, now)
  if (!perMinute) return ''
  return perMinute >= 1
    ? perMinute.toFixed(1) + ' chunks/min'
    : (perMinute * 60).toFixed(0) + ' chunks/hour'
}

export function remainingLabel (progress, now = Date.now()) {
  const perMinute = chunksPerMinute(progress, now)
  const left = Number(progress.chunksTotal) - Number(progress.chunksDone)
  if (!perMinute || !(left > 0)) return ''
  return 'about ' + duration((left / perMinute) * 60)
}

export function elapsedLabel (progress, now = Date.now()) {
  const since = Number(progress.translatingSince) || Number(progress.startedAt)
  return since ? duration((now - since) / 1000) : ''
}
