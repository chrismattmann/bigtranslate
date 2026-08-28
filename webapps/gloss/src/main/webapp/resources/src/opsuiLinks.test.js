import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isLineageField, opsuiProductUrl } from './opsuiLinks.js'

test('Solr lineage fields hop to OPSUI product pages', () => {
  assert.equal(isLineageField('InputFiles'), true)
  assert.equal(isLineageField('SplitFilename'), true)
  assert.equal(isLineageField('TsvFile'), true)
  assert.equal(isLineageField('title'), false)
  assert.equal(
    opsuiProductUrl('http://localhost:8080', 'computrabajo-do-20121106.tsv.aaaa'),
    'http://localhost:8080/opsui/#/product/computrabajo-do-20121106.tsv.aaaa'
  )
})
