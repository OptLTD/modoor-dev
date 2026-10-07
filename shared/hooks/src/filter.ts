import type { SchemaField } from './record'
import type { FilterDraft } from './recordPayload'

export type { FilterDraft } from './recordPayload'

/** 按字段类型返回可选运算符（与后端 field:OP 对齐） */
export function filterOps(f: SchemaField): { value: string; label: string }[] {
  const t = String(f.ftype || '').toUpperCase()
  const ALL = { value: 'ALL', label: '全部' }
  if (t === 'OPTIONAL' || t === 'RELATION') {
    return [
      ALL,
      { value: 'IN', label: '包含任一' },
      { value: 'EQ', label: '等于' },
      { value: 'NE', label: '不等于' },
      { value: 'NIL', label: '为空' },
      { value: 'NNL', label: '不为空' },
    ]
  }
  if (t === 'NUMERIC' || t === 'EXPENSE' || t === 'INTEGER') {
    return [
      ALL,
      { value: 'EQ', label: '等于' },
      { value: 'GT', label: '大于' },
      { value: 'GE', label: '大于等于' },
      { value: 'LT', label: '小于' },
      { value: 'LE', label: '小于等于' },
      { value: 'BTW', label: '介于' },
      { value: 'NIL', label: '为空' },
      { value: 'NNL', label: '不为空' },
    ]
  }
  if (t === 'DATETIME') {
    return [
      ALL,
      { value: 'EQ', label: '等于' },
      { value: 'GT', label: '晚于' },
      { value: 'GE', label: '起于' },
      { value: 'LT', label: '早于' },
      { value: 'LE', label: '止于' },
      { value: 'BTW', label: '介于' },
      { value: 'NIL', label: '为空' },
      { value: 'NNL', label: '不为空' },
    ]
  }
  return [
    ALL,
    { value: 'IN', label: '包含任一' },
    { value: 'LIKE', label: '包含' },
    { value: 'EQ', label: '等于' },
    { value: 'NE', label: '不等于' },
    { value: 'NIL', label: '为空' },
    { value: 'NNL', label: '不为空' },
  ]
}

export function defaultOp(f: SchemaField): string {
  return filterOps(f)[0]?.value || 'LIKE'
}

export function showValue(op: string): boolean {
  return op !== 'NIL' && op !== 'NNL'
}

export function needsValue(op: string): boolean {
  return op !== 'NIL' && op !== 'NNL' && op !== 'ALL'
}

export function needsValue2(op: string): boolean {
  return op === 'BTW'
}

export function isDraftActive(d: { op: string; value: string; value2: string } | undefined): boolean {
  if (!d || !d.op) return false
  if (d.op === 'ALL') return false
  if (d.op === 'NIL' || d.op === 'NNL') return true
  if (d.op === 'RCT') return String(d.value ?? '').trim() !== ''
  if (d.op === 'BTW') return !!d.value && !!d.value2
  return String(d.value ?? '').trim() !== ''
}

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

export function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/** 含当月共 n 个自然月（与 DateRange「近 N 月」一致） */
export function rangeLastNMonths(n: number): { start: string; end: string } {
  const months = Math.max(1, Math.floor(n) || 1)
  const t0 = new Date()
  t0.setHours(0, 0, 0, 0)
  const y = t0.getFullYear()
  const m = t0.getMonth()
  return {
    start: fmtDate(new Date(y, m - (months - 1), 1)),
    end: fmtDate(new Date(y, m + 1, 0)),
  }
}

/**
 * RCT/FTR token → 日期区间。
 * Token 命名与语义对齐 option-library/search/schema/query.go（RECENT_3_MONTH 等）。
 */
export function expandRctToken(token: string): { start: string; end: string } {
  const upper = String(token || '').trim().toUpperCase()
  const t0 = new Date()
  t0.setHours(0, 0, 0, 0)

  const addMonths = (d: Date, n: number) => {
    const x = new Date(d)
    x.setMonth(x.getMonth() + n)
    return x
  }
  const addDays = (d: Date, n: number) => {
    const x = new Date(d)
    x.setDate(x.getDate() + n)
    return x
  }
  const weekBounds = (previous = false) => {
    const wd = t0.getDay() === 0 ? 7 : t0.getDay() // Mon=1..Sun=7
    let start = addDays(t0, -(wd - 1))
    if (previous) start = addDays(start, -7)
    return { start, end: addDays(start, 6) }
  }

  if (upper === 'CURRENT_WEEK') {
    const w = weekBounds(false)
    return { start: fmtDate(w.start), end: fmtDate(w.end) }
  }
  if (upper === 'PREVIOUS_WEEK') {
    const w = weekBounds(true)
    return { start: fmtDate(w.start), end: fmtDate(w.end) }
  }
  if (upper === 'CURRENT_MONTH') return rangeLastNMonths(1)
  if (upper === 'PREVIOUS_MONTH') {
    const y = t0.getFullYear()
    const m = t0.getMonth()
    return {
      start: fmtDate(new Date(y, m - 1, 1)),
      end: fmtDate(new Date(y, m, 0)),
    }
  }
  if (upper === 'CURRENT_YEAR') {
    const y = t0.getFullYear()
    return { start: fmtDate(new Date(y, 0, 1)), end: fmtDate(new Date(y, 11, 31)) }
  }
  if (upper === 'PREVIOUS_YEAR') {
    const y = t0.getFullYear() - 1
    return { start: fmtDate(new Date(y, 0, 1)), end: fmtDate(new Date(y, 11, 31)) }
  }

  const recentDays: Record<string, number> = {
    RECENT_3_DAYS: 3,
    RECENT_1_WEEK: 7,
    RECENT_2_WEEK: 14,
  }
  if (upper in recentDays) {
    return { start: fmtDate(addDays(t0, -recentDays[upper])), end: fmtDate(t0) }
  }
  const recentMonths: Record<string, number> = {
    RECENT_1_MONTH: 1,
    RECENT_2_MONTH: 2,
    RECENT_3_MONTH: 3,
    RECENT_6_MONTH: 6,
  }
  if (upper in recentMonths) {
    return { start: fmtDate(addMonths(t0, -recentMonths[upper])), end: fmtDate(t0) }
  }
  const futureDays: Record<string, number> = {
    FUTURE_1_WEEK: 7,
    FUTURE_2_WEEK: 14,
  }
  if (upper in futureDays) {
    return { start: fmtDate(t0), end: fmtDate(addDays(t0, futureDays[upper])) }
  }
  const futureMonths: Record<string, number> = {
    FUTURE_1_MONTH: 1,
    FUTURE_2_MONTH: 2,
    FUTURE_3_MONTH: 3,
    FUTURE_6_MONTH: 6,
  }
  if (upper in futureMonths) {
    return { start: fmtDate(t0), end: fmtDate(addMonths(t0, futureMonths[upper])) }
  }

  return { start: fmtDate(addDays(t0, -30)), end: fmtDate(t0) }
}

/** DateRange start/end → FilterDraft；空区间返回 null（表示清除） */
export function draftFromDateRange(start: string, end: string): FilterDraft | null {
  let s = String(start ?? '').trim()
  let e = String(end ?? '').trim()
  if (s && e && s > e) {
    const tmp = s
    s = e
    e = tmp
  }
  if (!s && !e) return null
  if (s && e) return { op: 'BTW', value: s, value2: e }
  if (s) return { op: 'GE', value: s, value2: '' }
  return { op: 'LE', value: e, value2: '' }
}

/** FilterDraft → DateRange start/end（供快捷筛选 / FilterPanel 共用） */
export function dateRangeFromDraft(
  d: { op: string; value: string; value2: string } | undefined | null,
): { start: string; end: string } {
  if (!d || !isDraftActive(d)) return { start: '', end: '' }
  const op = d.op
  const v = String(d.value ?? '')
  const v2 = String(d.value2 ?? '')
  if (op === 'BTW') return { start: v, end: v2 }
  if (op === 'GE' || op === 'GTE' || op === 'GT') return { start: v, end: '' }
  if (op === 'LE' || op === 'LTE' || op === 'LT') return { start: '', end: v }
  if (op === 'EQ') return { start: v, end: v }
  return { start: '', end: '' }
}
