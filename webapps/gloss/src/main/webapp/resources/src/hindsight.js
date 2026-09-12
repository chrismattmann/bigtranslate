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
// What actually happened, against what the panels above say.
//
// The corpus stops in November 2013. More than a decade has passed, so the
// answers to its challenge questions are a matter of record rather than of
// opinion, and a panel that projects a line three months forward can be
// checked rather than admired.
//
// Every entry here carries a source. None of it is derived from the index:
// that is the point. The measured side of each comparison is computed live
// from Solr by the panel, and the two are put next to each other.
//
// Kept apart from the drawing for the same reason the rest of the arithmetic
// is, and because a claim about the world should be reviewable as text.

/** What the index is being checked against. */
export const SOURCES = {
  obgColombia2014: {
    label: 'Oxford Business Group, Colombia 2014',
    url: 'https://oxfordbusinessgroup.com/reports/colombia/2014-report/economy/homebuilding-and-ambitious-infrastructure-plans-drive-expansion'
  },
  obgPeru2015: {
    label: 'Oxford Business Group, Peru 2015',
    url: 'https://oxfordbusinessgroup.com/reports/peru/2015-report/economy'
  },
  bloombergPeso: {
    label: 'Bloomberg, Argentina devaluation, Jan 2014',
    url: 'https://www.bloomberg.com/news/articles/2014-01-23/argentina-s-peso-plunges-17-as-central-bank-scales-back-support'
  },
  brookingsPeso: {
    label: 'Brookings, Argentina’s Currency Devaluation',
    url: 'https://www.brookings.edu/articles/argentinas-currency-devaluation-back-to-the-future/'
  },
  kiaNuevoLeon: {
    label: 'Kia Pesquería, Nuevo León',
    url: 'https://mexicobusiness.news/automotive/news/kia-pesqueria-nuevo-leon'
  },
  audiPuebla: {
    label: 'Foreign investment in the Mexican automotive sector',
    url: 'https://www.tecma.com/foreign-investment-in-the-mexican-automotive-sector/'
  },
  ilo: {
    label: 'ILO, employment and informality in Latin America',
    url: 'https://www.ilo.org/sites/default/files/wcmsp5/groups/public/@americas/@ro-lima/@sro-port_of_spain/documents/genericdocument/wcms_819029.pdf'
  }
}

/**
 * Verdicts, strongest to weakest.
 *
 * "held" means the record agrees. "partial" means the direction was right and
 * the detail was not. "missed" means the index said one thing and the world
 * did another, which is the most useful entry in the table and the reason it
 * is not a list of successes.
 */
export const VERDICTS = {
  held: { label: 'Held up', rank: 3, colour: '#59a14f' },
  partial: { label: 'Partly', rank: 2, colour: '#e1a03c' },
  missed: { label: 'Missed it', rank: 1, colour: '#d1615d' },
  untestable: { label: 'Not testable', rank: 0, colour: '#9aa5b1' }
}

/**
 * The checks.
 *
 * `measure` names what the panel computes live, so the claim shown is the
 * index's own number rather than one written down here and left to rot.
 */
export const CHECKS = [
  {
    key: 'construction',
    question: 'Q6',
    claim: 'Construction had the fastest rising share of postings.',
    measure: { kind: 'sectorTrend', sector: 'construction' },
    happened: 'Colombia’s construction sector grew 9.8% in 2013 against '
      + '3.6% in 2012, on the back of the Vivienda Gratuita programme: '
      + '100,000 free homes, of which 98,500 were delivered by November 2015. '
      + 'Cundinamarca is the second largest region in this index.',
    verdict: 'held',
    sources: ['obgColombia2014']
  },
  {
    key: 'construction-after',
    question: 'Q1',
    claim: 'The projection continued construction upward past the corpus.',
    measure: { kind: 'sectorTrend', sector: 'construction' },
    happened: 'It did not continue. Peru’s construction sector grew 8.9% '
      + 'in 2013 and then slowed to 3.1% year on year in the first half of '
      + '2014, as the commodity supercycle ended and GDP growth fell to 3.1%. '
      + 'The corpus stops two months before that turn.',
    verdict: 'missed',
    sources: ['obgPeru2015']
  },
  {
    key: 'buenos-aires-retail',
    question: 'Q5',
    claim: 'Retail was thin in Federal Capital and Buenos Aires against a '
      + 'sector growing corpus-wide, and read as an opening.',
    measure: { kind: 'opportunity', region: /buenos aires|federal/i, sector: 'retail' },
    happened: 'The opposite arrived. The peso was devalued about 20% in '
      + 'January 2014, its largest fall since 2002; private consumption fell '
      + '1.2% in the first quarter and Argentina entered recession. A thin '
      + 'retail share ahead of a currency crisis is the leading edge of a '
      + 'contraction, not a gap in the market.',
    verdict: 'missed',
    sources: ['bloombergPeso', 'brookingsPeso']
  },
  {
    key: 'nuevo-leon',
    question: 'Q5',
    claim: 'Nuevo León was the strongest opening in the table.',
    measure: { kind: 'opportunity', region: /nuevo le/i },
    happened: 'Kia broke ground at Pesquería in August 2014, nine months '
      + 'after the corpus ends: a plant that grew to more than US$2.19bn and '
      + 'pulled an estimated US$1.5bn of supplier investment after it, '
      + 'establishing a regional automotive cluster.',
    verdict: 'partial',
    sources: ['kiaNuevoLeon']
  },
  {
    key: 'puebla',
    question: 'Q5',
    claim: 'Puebla was among the strongest openings.',
    measure: { kind: 'opportunity', region: /puebla/i },
    happened: 'Audi built a US$1.3bn plant at San José Chiapa near '
      + 'Puebla over 2013 to 2016. The region did expand sharply. What the '
      + 'index named was office and admin work; what arrived was an '
      + 'automotive cluster, which brings both.',
    verdict: 'partial',
    sources: ['audiPuebla']
  },
  {
    key: 'fulltime',
    question: 'Q12',
    claim: 'Full time work held about 84% of postings and did not move.',
    measure: { kind: 'fullTimeShare' },
    happened: 'Consistent with the regional record: formal full time '
      + 'employment in Latin America is stable over short horizons, and what '
      + 'moves is the informal share, which a job board does not advertise. '
      + 'A board of formal vacancies is the wrong instrument for the part of '
      + 'this labour market that actually changes.',
    verdict: 'held',
    sources: ['ilo']
  },
  {
    key: 'lifetime',
    question: 'Q2',
    claim: 'A posting of any kind stays up about a fortnight.',
    measure: { kind: 'lifetime' },
    happened: 'No published series tracks Computrabajo posting lifetimes, so '
      + 'there is nothing to check this against. It is reported as a '
      + 'measurement of the corpus rather than a finding about the labour '
      + 'market.',
    verdict: 'untestable',
    sources: []
  }
]

/** The sources one check cites, resolved. */
export function citations(check) {
  return (check.sources || [])
    .map((key) => SOURCES[key])
    .filter(Boolean)
}

/** How the checks came out, for the summary line. */
export function tally(checks) {
  const counts = { held: 0, partial: 0, missed: 0, untestable: 0 }
  ;(checks || CHECKS).forEach((c) => {
    if (counts[c.verdict] === undefined) {
      return
    }
    counts[c.verdict] += 1
  })
  return counts
}

/**
 * A sentence for the tally, which has to be able to say a poor result.
 *
 * Written from the counts rather than chosen, so a table that later goes
 * badly cannot keep a cheerful summary above it.
 */
export function verdictLine(counts) {
  const testable = counts.held + counts.partial + counts.missed
  if (testable === 0) {
    return 'Nothing here can be checked against the record.'
  }
  return `${counts.held} of ${testable} checks held up, `
    + `${counts.partial} partly, ${counts.missed} missed. `
    + `${counts.untestable} cannot be checked.`
}
