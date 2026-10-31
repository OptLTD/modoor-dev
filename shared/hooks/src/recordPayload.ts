import type { SchemaField } from './record'
import { readGlobalSettings } from './globalSettings'

function fieldHasFormula(extra: SchemaField['extra']): boolean {
  if (!extra) return false
  const f = extra.formula
  if (f != null && f !== '' && !(typeof f === 'boolean' && !f)) {
    if (typeof f === 'boolean') return true
    if (String(f).trim() !== '') return true
  }
  const d = extra.display
  return typeof d === 'string' && d.includes('[') && d.includes(']')
}

export type FilterDraft = {
  op: string
  value: string
  value2: string
}

export function fieldKey(f: SchemaField): string {
  if (f.uukey) return f.uukey
  if (f.index) return f.index
  if (f.group && f.field) return `${f.group}.${f.field}`
  if (f.field) return `basic.${f.field}`
  return ''
}

export function rowUUKey(row: Record<string, unknown> | null | undefined): string {
  if (!row) return ''
  // 聚合行：basic.uukey 常被 CNT 占用，稳定主键在 $digest.uukey$
  const digest = row['$digest.uukey$']
  if (digest != null && String(digest).trim() !== '') return String(digest).trim()
  const direct = row.uukey ?? row['basic.uukey']
  if (direct != null && String(direct).trim() !== '') return String(direct).trim()
  return ''
}

export function pickFieldValue(row: Record<string, unknown> | null | undefined, f: SchemaField): unknown {
  if (!row) return ''
  const key = fieldKey(f)
  if (key in row) return row[key]
  if (f.index && f.index in row) return row[f.index]
  if (f.field && f.field in row) return row[f.field]
  const nested = row[f.group]
  if (nested && typeof nested === 'object') {
    return (nested as Record<string, unknown>)[f.field]
  }
  return undefined
}

function formatWithPattern(
  parts: { year: string; month: string; day: string; hour: string; minute: string; second: string },
  pattern: string,
): string {
  return pattern
    .replace(/YYYY/g, parts.year)
    .replace(/MM/g, parts.month)
    .replace(/DD/g, parts.day)
    .replace(/HH/g, parts.hour)
    .replace(/mm/g, parts.minute)
    .replace(/ss/g, parts.second)
}

const HAS_OFFSET = /[zZ]$|[+-]\d{2}:?\d{2}$/

/** 带时区的日期折到公司时区的日历日。裸 YYYY-MM-DD 原样截断。 */
function calendarInCompanyZone(raw: string, pattern: 'YYYY-MM-DD' | 'YYYY-MM'): string | null {
  if (!HAS_OFFSET.test(raw)) return null
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return null
  try {
    const prefs = readGlobalSettings()
    return formatInTimeZone(date, prefs.timezone || 'Asia/Shanghai', pattern)
  } catch {
    return null
  }
}

function formatInTimeZone(date: Date, timeZone: string, pattern: string): string {
  const bits = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const pick = (type: string) => bits.find((p) => p.type === type)?.value || ''
  let hour = pick('hour')
  if (hour === '24') hour = '00'
  return formatWithPattern(
    {
      year: pick('year'),
      month: pick('month'),
      day: pick('day'),
      hour,
      minute: pick('minute'),
      second: pick('second'),
    },
    pattern,
  )
}

/** DATETIME uses the company time format. Offset values are shifted into the company timezone. */
export function formatDateTimeDisplay(
  raw: unknown,
  mode: boolean | DateTimeKind = false,
): string {
  if (raw == null || raw === '') return ''
  const s = String(raw).trim()
  const kind: DateTimeKind = mode === true
    ? 'ONLYDATE' : mode === false
    ? 'DATETIME' : mode
  if (kind === 'ONLYMONTH') return calendarInCompanyZone(s, 'YYYY-MM') || s.slice(0, 7)
  if (kind === 'ONLYDATE') return calendarInCompanyZone(s, 'YYYY-MM-DD') || s.slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}/.test(s)) {
    return /^\d{4}-\d{2}/.test(s) ? s.slice(0, 7) : s
  }
  const prefs = readGlobalSettings()
  const pattern = prefs.timeFormat || 'YYYY-MM-DD HH:mm:ss'
  if (HAS_OFFSET.test(s)) {
    const date = new Date(s)
    if (!Number.isNaN(date.getTime())) {
      try {
        return formatInTimeZone(date, prefs.timezone || 'Asia/Shanghai', pattern)
      } catch {
        /* unknown zone: fall through */
      }
    }
  }
  const naive = s.match(/^(\d{4})[-/](\d{2})[-/](\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (!naive) return s.slice(0, 19).replace('T', ' ')
  return formatWithPattern(
    {
      year: naive[1],
      month: naive[2],
      day: naive[3],
      hour: naive[4] || '00',
      minute: naive[5] || '00',
      second: naive[6] || '00',
    },
    pattern,
  )
}

export function formatDateInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
  const s = String(raw).trim()
  return calendarInCompanyZone(s, 'YYYY-MM-DD') || s.slice(0, 10)
}

export function formatMonthInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
  const s = String(raw).trim()
  return calendarInCompanyZone(s, 'YYYY-MM') || s.slice(0, 7)
}

/** Excel / 粘贴常见：斜杠日期、未补零小时、12 小时制 AM/PM、T 与空格混用 */
const LOOSE_DT =
  /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?$/i
const LOOSE_YM = /^(\d{4})[-/.](\d{1,2})/

function pad2(n: number | string): string {
  return String(n).padStart(2, '0')
}

function parseLooseDateTime(raw: string): {
  year: string
  month: string
  day: string
  hour: string
  minute: string
  second: string
  hasTime: boolean
} | null {
  const m = raw.trim().match(LOOSE_DT)
  if (!m) return null
  let hour = Number(m[4] ?? 0)
  const hasTime = m[4] != null
  const ap = (m[7] || '').toUpperCase()
  if (ap === 'PM' && hour < 12) hour += 12
  if (ap === 'AM' && hour === 12) hour = 0
  return {
    year: m[1],
    month: pad2(m[2]),
    day: pad2(m[3]),
    hour: pad2(hour),
    minute: pad2(m[5] ?? 0),
    second: pad2(m[6] ?? 0),
    hasTime,
  }
}

export function formatDateTimeInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
  const loose = parseLooseDateTime(String(raw))
  if (loose) {
    return `${loose.year}-${loose.month}-${loose.day}T${loose.hour}:${loose.minute}`
  }
  const s = String(raw).replace(' ', 'T')
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) return s.slice(0, 16)
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return `${s.slice(0, 10)}T00:00`
  return s
}

export type DateTimeKind = 'DATETIME' | 'ONLYDATE' | 'ONLYMONTH'

export function dateTimeKindFromExtra(extra: Record<string, unknown> | undefined | null): DateTimeKind {
  const dt = String(extra?.datetime || extra?.dataType || '').toUpperCase()
  if (dt === 'ONLYMONTH') return 'ONLYMONTH'
  if (dt === 'ONLYDATE') return 'ONLYDATE'
  return 'DATETIME'
}

/**
 * 提交前把表格/Excel 里的松散时间补齐为后端可解析的 ISO 形态。
 * 例：`2026/10/28 5:26 PM` → `2026-10-28T17:26:00`
 */
export function normalizeDateTimeStoreValue(
  raw: string,
  kind: boolean | DateTimeKind = false,
): string {
  const s = String(raw || '').trim()
  if (!s) return ''
  const mode: DateTimeKind = kind === true ? 'ONLYDATE' : kind === false ? 'DATETIME' : kind
  const loose = parseLooseDateTime(s)
  if (loose) {
    const ymd = `${loose.year}-${loose.month}-${loose.day}`
    if (mode === 'ONLYMONTH') return `${loose.year}-${loose.month}-01T00:00:00`
    if (mode === 'ONLYDATE') return ymd
    return `${ymd}T${loose.hour}:${loose.minute}:${loose.second}`
  }
  if (mode === 'ONLYMONTH') {
    const ym = s.match(LOOSE_YM)
    if (ym) return `${ym[1]}-${pad2(ym[2])}-01T00:00:00`
    const slice = s.length >= 7 ? s.slice(0, 7) : s
    // ORM 存完整时间；展示仍按月。取当月 1 日便于 timeTerm。
    return /^\d{4}-\d{2}$/.test(slice) ? `${slice}-01T00:00:00` : s
  }
  if (mode === 'ONLYDATE') {
    const d = parseLooseDateTime(`${s.slice(0, 10)}`)
    return d ? `${d.year}-${d.month}-${d.day}` : s.slice(0, 10)
  }
  // 已带偏移的 ISO 等：只把首个日期-时间空格换成 T
  return s.includes('T') ? s : s.replace(' ', 'T')
}

function payloadScalar(value: string | string[]): string | string[] {
  if (Array.isArray(value)) return value.map(String).filter((s) => s.trim())
  return String(value ?? '')
}

/** 表单初始值 */
export function formFieldDefault(
  row: Record<string, unknown> | null | undefined,
  f: SchemaField,
): string | string[] {
  const multi = !!(f.extra?.multiple === true || f.extra?.multiple === 'true')
  const raw = pickFieldValue(row, f)
  if (raw == null || raw === '') return multi ? [] : ''
  if (String(f.ftype).toUpperCase() === 'DATETIME' && !Array.isArray(raw)) {
    const kind = dateTimeKindFromExtra(f.extra)
    if (kind === 'ONLYMONTH') return formatMonthInputValue(raw)
    if (kind === 'ONLYDATE') return formatDateInputValue(raw)
    return formatDateTimeInputValue(raw)
  }
  if (multi) {
    if (Array.isArray(raw)) return raw.map(String)
    return String(raw)
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
  }
  return Array.isArray(raw) ? raw.join(',') : String(raw)
}

export function assignFieldPayload(
  payload: Record<string, unknown>,
  f: SchemaField,
  value: string | string[],
) {
  let v: unknown = payloadScalar(value)
  if (String(f.ftype).toUpperCase() === 'DATETIME') {
    v = normalizeDateTimeStoreValue(String(v ?? ''), dateTimeKindFromExtra(f.extra))
  }
  const key = fieldKey(f)
  if (key) payload[key] = v
  if (f.group === 'basic' || !f.group) {
    if (f.field) payload[f.field] = v
  }
}

export function injectRowIdentity(
  payload: Record<string, unknown>,
  row: Record<string, unknown> | null | undefined,
) {
  const uk = rowUUKey(row)
  if (!uk) return
  payload.uukey = uk
  payload['basic.uukey'] = uk
}

/** Sheet 行 → upsert batch 项（空值也带上，便于清空数值列；公式列只读不提交） */
export function rowToUpsertPayload(
  row: Record<string, string>,
  fields: SchemaField[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const uk = row.uukey?.trim()
  if (uk) injectRowIdentity(out, { uukey: uk })

  for (const f of fields) {
    if (fieldHasFormula(f.extra)) continue
    const fk = fieldKey(f)
    const raw = row[fk] ?? row[f.field] ?? ''
    const v = raw == null ? '' : String(raw)
    if (f.field === 'uukey' && !v.trim()) continue
    assignFieldPayload(out, f, v)
  }
  return out
}

/** 将列筛选草稿转为 search query（field / field:OP） */
export function buildListQuery(
  applied: Record<string, FilterDraft>,
  fields: SchemaField[],
): Record<string, unknown> | undefined {
  const q: Record<string, unknown> = {}
  for (const [fk, draft] of Object.entries(applied)) {
    if (!draft?.op) continue
    const f = fields.find((x) => fieldKey(x) === fk)
    const key = f ? fieldKey(f) : fk
    let op = draft.op
    if (op === 'ALL') continue
    // 前端 GE/LE → 后端 GTE/LTE
    if (op === 'GE') op = 'GTE'
    if (op === 'LE') op = 'LTE'
    if (op === 'NIL' || op === 'NNL') {
      // 后端仅识别 NIL：true=为空，false=不为空
      q[`${key}:NIL`] = op === 'NIL'
      continue
    }
    if (op === 'IN') {
      const arr = String(draft.value ?? '')
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean)
      if (arr.length) q[`${key}:IN`] = arr
      continue
    }
    if (!String(draft.value ?? '').trim() && op !== 'EQ') continue
    if (op === 'BTW') {
      if (!draft.value || !draft.value2) continue
      q[`${key}:BTW`] = [draft.value, draft.value2]
      continue
    }
    if (op === 'RCT') {
      if (!String(draft.value ?? '').trim()) continue
      q[`${key}:RCT`] = draft.value
      continue
    }
    if (op === 'EQ') {
      q[key] = draft.value
      continue
    }
    q[`${key}:${op}`] = draft.value
  }
  return Object.keys(q).length ? q : undefined
}

export function mergeListQuery(
  applied?: Record<string, unknown>,
  fixed?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  // 用户筛选覆盖视图默认 query（同 key 时 applied 优先）
  const merged = { ...(fixed || {}), ...(applied || {}) }
  return Object.keys(merged).length ? merged : undefined
}
