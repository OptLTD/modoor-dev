import type { SchemaField } from './record'

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

export function formatDateTimeDisplay(
  raw: unknown,
  mode: boolean | DateTimeKind = false,
): string {
  if (raw == null || raw === '') return ''
  const s = String(raw)
  const kind: DateTimeKind = mode === true 
    ? 'ONLYDATE' : mode === false 
    ? 'DATETIME' : mode
  if (/^\d{4}-\d{2}/.test(s)) {
    if (kind === 'ONLYMONTH') return s.slice(0, 7)
    if (kind === 'ONLYDATE') return s.slice(0, 10)
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
      return s.includes('T') ? s.replace('T', ' ').slice(0, 19) : s.slice(0, 19).replace('T', ' ')
    }
    return s.slice(0, 7)
  }
  return s
}

export function formatDateInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
  return String(raw).slice(0, 10)
}

export function formatMonthInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
  return String(raw).slice(0, 7)
}

export function formatDateTimeInputValue(raw: unknown): string {
  if (raw == null || raw === '') return ''
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

export function normalizeDateTimeStoreValue(
  raw: string,
  kind: boolean | DateTimeKind = false,
): string {
  const s = String(raw || '').trim()
  if (!s) return ''
  const mode: DateTimeKind = kind === true ? 'ONLYDATE' : kind === false ? 'DATETIME' : kind
  if (mode === 'ONLYMONTH') {
    const ym = s.length >= 7 ? s.slice(0, 7) : s
    // ORM 存完整时间；展示仍按月。取当月 1 日便于 timeTerm。
    return /^\d{4}-\d{2}$/.test(ym) ? `${ym}-01T00:00:00` : s
  }
  if (mode === 'ONLYDATE') return s.slice(0, 10)
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

/** Sheet 行 → upsert batch 项 */
export function rowToUpsertPayload(
  row: Record<string, string>,
  fields: SchemaField[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const uk = row.uukey?.trim()
  if (uk) injectRowIdentity(out, { uukey: uk })

  for (const f of fields) {
    const fk = fieldKey(f)
    const raw = row[fk] ?? row[f.field] ?? ''
    const v = raw == null ? '' : String(raw)
    if (!v.trim() && f.field !== 'uukey') continue
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
