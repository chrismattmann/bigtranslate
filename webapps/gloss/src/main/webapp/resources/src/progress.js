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

export function percent (progress) {
  const total = Number(progress.chunksTotal)
  if (!total) return 0
  const done = Number(progress.chunksDone) || 0
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
