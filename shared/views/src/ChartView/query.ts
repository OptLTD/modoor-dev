import type { ChartCard } from './types'

/** charts.json query → searchRecords / TableDrawer.fixedQuery。 */
export function chartSearchQuery(card: ChartCard): Record<string, unknown> {
  const inner = { ...(card.query?.query || {}) }
  const hasNamedOr = Object.keys(inner).some((k) => k.toUpperCase().startsWith('GROUP:OR'))
  if (String(card.query?.logic || '').toUpperCase() === 'OR' && !hasNamedOr) {
    return { 'GROUP:OR': inner }
  }
  return inner
}
