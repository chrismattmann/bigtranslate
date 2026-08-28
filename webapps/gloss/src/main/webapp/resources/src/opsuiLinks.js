export const LINEAGE_FIELDS = {
  InputFiles: true,
  SplitFilename: true,
  TsvFile: true
}

export function isLineageField(name) {
  return Boolean(LINEAGE_FIELDS[name])
}

export function opsuiProductUrl(origin, name) {
  if (!name) {
    return ''
  }
  return String(origin || '') + '/opsui/#/product/' + encodeURIComponent(name)
}
