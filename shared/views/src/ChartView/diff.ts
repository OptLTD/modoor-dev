import type { ChartValue } from './types'

export type DiffScope = 'current' | 'previous' | 'earlier'

const TERM_START = 26

export function utermOf(day: Date, start = TERM_START): number {
  const cut = start >= 1 && start <= 28 ? start : TERM_START
  let y = day.getFullYear()
  let m = day.getMonth() + 1
  if (day.getDate() >= cut) {
    m += 1
    if (m > 12) {
      y += 1
      m = 1
    }
  }
  return y * 100 + m
}

export function prevUterm(uterm: number): number {
  let y = Math.floor(uterm / 100)
  let m = uterm % 100 - 1
  if (m < 1) {
    y -= 1
    m = 12
  }
  return y * 100 + m
}

export function scopeUterm(scope: DiffScope, now = new Date(), start = TERM_START): number {
  let term = utermOf(now, start)
  const back = scope === 'previous' ? 1 : scope === 'earlier' ? 2 : 0
  for (let i = 0; i < back; i += 1) term = prevUterm(term)
  return term
}

export function queryForTerm(source: ChartValue, uterm: number): Record<string, unknown> {
  const field = String(source.term || 'basic.uterm')
  return { ...(source.query || {}), [field]: uterm }
}

export function reportUrl(source: ChartValue, uterm: number): string {
  const path = String(source.path || '')
  if (!path.startsWith('/api/')) throw new Error('报表路径无效')
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(source.query || {})) {
    if (value == null || typeof value === 'object') continue
    params.set(key, String(value))
  }
  params.set('uterm', String(uterm))
  return `${path}?${params.toString()}`
}

export function sumTotals(totals: Record<string, unknown> | null | undefined, keys: string[]): number {
  let total = 0
  for (const key of keys) {
    const n = Number(totals?.[key] ?? 0)
    if (Number.isFinite(n)) total += n
  }
  return Math.round(total * 100) / 100
}

export function diffAmount(left: number, right: number): number {
  return Math.round((left - right) * 100) / 100
}
