import type { SchemaField } from './record'
import {
  dateTimeKindFromExtra,
  formatDateTimeDisplay,
  pickFieldValue,
  type DateTimeKind,
} from './recordPayload'

export type ReferDict = Record<string, Record<string, unknown>[]>
export type FormMode = 'create' | 'modify'

function extraStr(f: SchemaField, key: string, fallback = '') {
  const v = f.extra?.[key]
  if (v == null || v === '') return fallback
  return String(v)
}

function extraBool(f: SchemaField, key: string) {
  const v = f.extra?.[key]
  return v === true || v === 1 || v === '1' || String(v).toLowerCase() === 'true'
}

function ftypeOf(f: SchemaField) {
  return String(f.ftype || '').toUpperCase()
}

export function referGet(obj: Record<string, unknown> | null | undefined, key: string): unknown {
  if (!obj || !key) return undefined
  if (key in obj) return obj[key]
  const tail = key.split('.').pop()
  if (tail && tail in obj) return obj[tail]
  return undefined
}

export function fieldRefer(f: SchemaField): { using: string; keyby: string; txtby: string } | null {
  const ft = ftypeOf(f)
  if (f.refer?.using) {
    return {
      using: f.refer.using,
      keyby: f.refer.keyby || (ft === 'RELATION' ? 'basic.uukey' : 'uukey'),
      txtby: f.refer.txtby || (ft === 'RELATION' ? 'basic.name' : 'label'),
    }
  }
  if (ft === 'RELATION') {
    const using = String(f.extra?.relation || '')
    if (!using) return null
    return {
      using,
      keyby: String(f.extra?.dataKey || 'basic.uukey'),
      txtby: String(f.extra?.textKey || 'basic.name'),
    }
  }
  if (ft === 'OPTIONAL') {
    return { using: f.uukey, keyby: 'uukey', txtby: 'label' }
  }
  return null
}

function referLabel(refer: NonNullable<ReturnType<typeof fieldRefer>>, dict: Record<string, unknown>[], id: string) {
  const hit = dict.find((x) => String(referGet(x, refer.keyby) ?? '') === id)
  return hit ? String(referGet(hit, refer.txtby) ?? id) : id
}

export function convertReferValue(f: SchemaField, rowValue: unknown, refers?: ReferDict): string {
  const refer = fieldRefer(f)
  if (!refer?.using || rowValue == null || rowValue === '') {
    return rowValue == null ? '' : String(rowValue)
  }
  const multi = Array.isArray(rowValue) || extraBool(f, 'multiple')
  const ids = multi
    ? (Array.isArray(rowValue) ? rowValue : String(rowValue).split(/[,\n]/))
        .map((v) => String(v ?? '').trim())
        .filter(Boolean)
    : [String(rowValue)]
  const dict = refers?.[refer.using]
  if (!Array.isArray(dict) || !dict.length) return ids.join('、')
  return ids.map((id) => referLabel(refer, dict, id)).join('、')
}

export function displayFieldValue(
  row: Record<string, unknown>,
  f: SchemaField,
  ctx?: { refers?: ReferDict },
): string {
  const raw = pickFieldValue(row, f)
  const ft = ftypeOf(f)
  if (ft === 'DATETIME') return formatDateTimeDisplay(raw, dateTimeKind(f))
  if (ft === 'OPTIONAL' || ft === 'RELATION') {
    return convertReferValue(f, raw, ctx?.refers)
  }
  if (raw == null || raw === '') return ''
  if (isNumericField(f)) return formatNumericDisplay(raw, f)
  return String(raw)
}

export function formatNumericDisplay(raw: unknown, f: SchemaField): string {
  const n = Number(raw)
  if (!Number.isFinite(n)) return String(raw ?? '')
  const ft = ftypeOf(f)
  if (ft === 'INTEGER') {
    return new Intl.NumberFormat('zh-CN', {
      useGrouping: false,
      maximumFractionDigits: 0,
    }).format(n)
  }
  const precision = Number(f.extra?.precision)
  const digits =
    Number.isFinite(precision) && precision >= 0 ? Math.floor(precision) : 2
  const mode = extraStr(f, 'roundMode').toLowerCase() || 'round'
  const factor = 10 ** digits
  let rounded = n
  if (digits >= 0) {
    if (mode === 'floor') rounded = Math.floor(n * factor + Number.EPSILON) / factor
    else if (mode === 'ceil') rounded = Math.ceil(n * factor - Number.EPSILON) / factor
    else rounded = Math.round(n * factor + Number.EPSILON * (n >= 0 ? 1 : -1)) / factor
  }
  // 按 precision 截断展示；尾随 0 不强制（避免列宽 …）
  const body = new Intl.NumberFormat('zh-CN', {
    useGrouping: false,
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(rounded)
  // valueFmt=percent：数值已是百分数（如 97.4），仅加 % 后缀
  if (extraStr(f, 'valueFmt').toLowerCase() === 'percent') {
    return `${body}%`
  }
  return body
}

export function isNumericField(f: SchemaField) {
  const t = ftypeOf(f)
  return t === 'NUMERIC' || t === 'EXPENSE' || t === 'INTEGER'
}

export function referOptions(
  f: SchemaField,
  refers?: ReferDict,
): { label: string; value: string; parent?: string }[] {
  const refer = fieldRefer(f)
  if (refer?.using) {
    const dict = refers?.[refer.using] || []
    return dict
      .map((item) => {
        const value = String(referGet(item, refer.keyby) ?? '')
        const label = String(referGet(item, refer.txtby) ?? value)
        const parent = String(referGet(item, 'parent') ?? '')
        return { value, label, parent }
      })
      .filter((o) => o.value)
      .filter((o, i, arr) => arr.findIndex((x) => x.value === o.value) === i)
  }
  const raw = (f.options ||
    (f.extra?.options as { label?: string; value?: string; uukey?: string; parent?: string }[] | undefined)) as
    | { label?: string; value?: string; uukey?: string; parent?: string }[]
    | undefined
  return (raw || [])
    .map((o) => ({
      label: String(o.label || o.uukey || o.value || ''),
      value: String(o.uukey ?? o.value ?? ''),
      parent: String(o.parent || ''),
    }))
    .filter((o) => o.value)
}

export function mergeRefers(schemaRefers?: ReferDict, resultRefers?: ReferDict): ReferDict {
  return { ...(schemaRefers || {}), ...(resultRefers || {}) }
}

export function normalizeReferDict(raw?: Record<string, unknown> | ReferDict): ReferDict {
  const out: ReferDict = {}
  if (!raw) return out
  for (const [k, v] of Object.entries(raw)) {
    if (Array.isArray(v)) out[k] = v as Record<string, unknown>[]
  }
  return out
}

/** 表单/表格 RELATION 下拉：按 refer.using 拉取关联模型（优先 tables.relation，回退 default） */
export async function loadDropdownRefers(
  fields: SchemaField[],
  schemaRefers?: ReferDict,
  extra?: ReferDict,
): Promise<ReferDict> {
  const { searchRecords } = await import('./record')
  let merged = mergeRefers(normalizeReferDict(schemaRefers), extra || {})
  const relationModels = new Set<string>()
  for (const f of fields) {
    if (ftypeOf(f) !== 'RELATION') continue
    const refer = fieldRefer(f)
    if (refer?.using) relationModels.add(refer.using)
  }
  if (!relationModels.size) return merged
  const loaded: ReferDict = {}
  await Promise.all(
    [...relationModels].map(async (model) => {
      try {
        const res = await searchRecords(model, 'relation', 1, 500)
        loaded[model] = (res.values || []) as Record<string, unknown>[]
      } catch {
        loaded[model] = []
      }
    }),
  )
  return mergeRefers(merged, loaded)
}

/** 按 schema.sticky 顺序排列可见列 */
export function applyStickyOrder(keys: string[], sticky: string[]): string[] {
  const set = new Set(sticky)
  const head = sticky.filter((k) => keys.includes(k))
  const rest = keys.filter((k) => !set.has(k))
  return [...head, ...rest]
}

export function isSortableField(f: SchemaField) {
  if (ftypeOf(f) === 'UPLOADS') return false
  return !!(f.uukey || f.index)
}

/** 排序请求用逻辑键（uukey） */
export function sortIndexField(f: SchemaField) {
  return f.uukey || f.index || ''
}

export function isImplicit(f: SchemaField) {
  return extraBool(f, 'implicit') || extraBool(f, 'computed')
}

export function isRequired(f: SchemaField) {
  return extraBool(f, 'required')
}

export function isMultiple(f: SchemaField) {
  return extraBool(f, 'multiple')
}

type FieldOption = { label?: string; value?: string; uukey?: string; short?: string }

function optionList(f: SchemaField): FieldOption[] {
  const raw = f.options || (f.extra?.options as FieldOption[] | undefined)
  return Array.isArray(raw) ? raw : []
}

/** 多选枚举且选项带 short：列表用短标签，而不是拼成长文案。 */
export function isTagField(f: SchemaField) {
  if (ftypeOf(f) !== 'OPTIONAL' || !isMultiple(f)) return false
  return optionList(f).some((o) => String(o.short || '').trim())
}

export function tagChips(row: Record<string, unknown>, f: SchemaField) {
  if (!isTagField(f)) return []
  const raw = pickFieldValue(row, f)
  const ids = (Array.isArray(raw) ? raw : String(raw ?? '').split(/[,\n]/))
    .map((v) => String(v ?? '').trim())
    .filter(Boolean)
  const opts = optionList(f)
  return ids.map((id) => {
    const hit = opts.find((o) => String(o.uukey ?? o.value ?? '') === id)
    const label = String(hit?.label || id)
    const short = String(hit?.short || '').trim() || label.slice(0, 1)
    return { value: id, label, short }
  })
}

export function editableMode(f: SchemaField) {
  if (extraBool(f, 'computed')) return 'NEVER'
  return extraStr(f, 'editable', 'ALWAYS').toUpperCase()
}

export function disabledMode(f: SchemaField) {
  return extraStr(f, 'disabled', 'NEVER').toUpperCase()
}

export function isFieldEditable(f: SchemaField, mode: FormMode) {
  const disabled = disabledMode(f)
  if (disabled === 'ALWAYS' || disabled === 'UPSERT') return false
  if (mode === 'create' && disabled === 'INSERT') return false
  if (mode === 'modify' && disabled === 'UPDATE') return false

  switch (editableMode(f)) {
    case 'NEVER':
      return false
    case 'INSERT':
      return mode === 'create'
    case 'UPDATE':
      return mode === 'modify'
    case 'UPSERT':
    case 'ALWAYS':
    case '':
      return true
    default:
      return true
  }
}

export function isLongTextField(f: SchemaField) {
  const dt = extraStr(f, 'dataType').toUpperCase()
  if (dt === 'LONGTEXT' || dt === 'RICHTEXT') return true
  return ftypeOf(f) === 'LONGTEXT'
}

/** 业务时间紧跟编号，作为核心字段靠前。 */
function pinUtime(list: SchemaField[]) {
  const utime = list.filter((f) => f.uukey === 'basic.utime')
  if (!utime.length) return list
  const rest = list.filter((f) => f.uukey !== 'basic.utime')
  const afterKey = rest.findIndex((f) => f.uukey === 'basic.uukey')
  if (afterKey >= 0) {
    rest.splice(afterKey + 1, 0, ...utime)
    return rest
  }
  return [...utime, ...rest]
}

/** 表单可见字段：shown≠false，非隐式；utime 靠前，长文本排后 */
export function formVisibleFields(fields: SchemaField[]) {
  const visible = fields.filter(
    (f) => f.field && f.field !== 'model' && f.shown !== false && !isImplicit(f),
  )
  const normal: SchemaField[] = []
  const longText: SchemaField[] = []
  for (const f of visible) {
    if (isLongTextField(f)) longText.push(f)
    else normal.push(f)
  }
  return [...pinUtime(normal), ...longText]
}

export function isEmptyValue(v: string | string[] | undefined | null) {
  if (v == null) return true
  if (Array.isArray(v)) return v.length === 0
  return !String(v).trim()
}

export function dateTimeKind(f: SchemaField): DateTimeKind {
  return dateTimeKindFromExtra(f.extra)
}

export function isOnlyDate(f: SchemaField) {
  return dateTimeKind(f) === 'ONLYDATE'
}

export function isOnlyMonth(f: SchemaField) {
  return dateTimeKind(f) === 'ONLYMONTH'
}
