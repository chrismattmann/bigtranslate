const services = () => `${window.location.origin}/gloss-services`

async function readJson(response) {
  const text = await response.text()
  let body = {}
  if (text) {
    try {
      body = JSON.parse(text)
    } catch (e) {
      body = { error: text }
    }
  }
  if (!response.ok) {
    const message = body.error || response.statusText || `HTTP ${response.status}`
    throw new Error(message)
  }
  return body
}

export function getStatus() {
  return fetch(`${services()}/bt/status`).then(readJson)
}

export function getSummary() {
  return fetch(`${services()}/service/summary`).then(readJson)
}

export function getMap() {
  return fetch(`${services()}/service/map`).then(readJson)
}

function filterParams(filters) {
  const params = new URLSearchParams()
  ;(filters || []).forEach((f) => {
    if (f.field && f.value) {
      params.append('field', f.field)
      params.append('value', f.value)
    }
  })
  return params
}

export function getTable(query, start, rows, filters, sort, dir) {
  const params = filterParams(filters)
  if (query) {
    params.set('q', query)
  }
  params.set('start', String(start || 0))
  params.set('rows', String(rows || 25))
  if (sort) {
    params.set('sort', sort)
  }
  if (dir) {
    params.set('dir', dir)
  }
  return fetch(`${services()}/service/table?${params.toString()}`).then(readJson)
}

export function getRecord(id) {
  const params = new URLSearchParams()
  params.set('id', id)
  return fetch(`${services()}/service/record?${params.toString()}`).then(readJson)
}

export function getFacets(query, filters) {
  const params = filterParams(filters)
  if (query) {
    params.set('q', query)
  }
  return fetch(`${services()}/service/facets?${params.toString()}`).then(readJson)
}

/**
 * A json.facet query, straight through to Solr.
 *
 * The Analytics panels ask questions the service layer has no opinion about
 * -- nine sectors crossed with eighteen months crossed with a dozen regions
 * -- and gloss-services already exposes the core for exactly this. Adding an
 * endpoint per chart would put the arithmetic on the far side of a network
 * call from the chart that has to explain it.
 */
export function solrFacet(facet, params) {
  const query = new URLSearchParams()
  query.set('q', (params && params.q) || '*:*')
  query.set('rows', '0')
  query.set('wt', 'json')
  ;((params && params.fq) ? [].concat(params.fq) : []).forEach((fq) => {
    query.append('fq', fq)
  })
  query.set('json.facet', JSON.stringify(facet))
  return fetch(`${services()}/solr/bigtranslate/select?${query.toString()}`)
    .then(readJson)
}

export function getProgress() {
  return fetch(`${services()}/service/progress`).then(readJson)
}

export function getOodtStatus() {
  return fetch(`${services()}/service/status/oodt`).then(readJson)
}

export function getLog() {
  return fetch(`${services()}/bt/log`).then((r) => r.text())
}

export function translate(path, exclude) {
  const body = { path }
  if (exclude) {
    body.exclude = exclude
  }
  return fetch(`${services()}/bt/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(readJson)
}

export function reset() {
  return fetch(`${services()}/bt/reset`, { method: 'POST' }).then(readJson)
}
