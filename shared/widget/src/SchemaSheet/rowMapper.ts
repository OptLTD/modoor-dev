import type { SchemaField } from '@modoor/hooks'
import { formFieldDefault, fieldKey, formatDateTimeDisplay, pickFieldValue } from '@modoor/hooks'
import type { ReferDict } from '@modoor/hooks'
import { dateTimeKind } from '@modoor/hooks'
import type { SheetRow } from './types'
import { isDropdownField, isSerial } from './fieldUtils'
import { normalizeDropdownCellValue } from './dropdown'

export function isSheetRowEmpty(r: SheetRow): boolean {
  return !Object.values(r).some((v) => String(v).trim() !== '')
}

export function syncRowUUKey(r: SheetRow, fields: SchemaField[]) {
  const ukField = fields.find((f) => isSerial(f))
  const fromCol = ukField ? String(r[fieldKey(ukField)] ?? '').trim() : ''
  const uk = fromCol || String(r.uukey ?? '').trim()
  if (uk) {
    r.uukey = uk
    if (ukField) r[fieldKey(ukField)] = uk
  }
}

function sheetRawValue(raw: Record<string, unknown>, f: SchemaField): string {
  const v = pickFieldValue(raw, f)
  if (Array.isArray(v)) return v.filter(Boolean).join(',')
  if (String(v ?? '').trim()) return String(v)

  const fk = fieldKey(f)
  const direct = raw[fk] ?? raw[f.field]
  if (direct != null && typeof direct !== 'object') return String(direct)

  if (direct && typeof direct === 'object') {
    const o = direct as Record<string, unknown>
    const uk = o.uukey ?? o['basic.uukey']
    if (uk != null && String(uk).trim()) return String(uk)
  }
  return ''
}

export function fromSearchRow(
  raw: Record<string, unknown>,
  fields: SchemaField[],
  referCache: ReferDict,
): SheetRow {
  const r: SheetRow = {}
  for (const f of fields) {
    const fk = fieldKey(f)
    let v = sheetRawValue(raw, f)
    if (isDropdownField(f)) v = normalizeDropdownCellValue(f, v, referCache)
    // 与 sheet calendar 格式对齐：ONLYDATE→日期；完整 DATETIME→YYYY-MM-DD HH:mm
    if (String(f.ftype).toUpperCase() === 'DATETIME' && v) {
      v = formatDateTimeDisplay(v, dateTimeKind(f)) || v
    }
    r[fk] = v
  }
  syncRowUUKey(r, fields)
  return r
}

export function emptyRow(
  fields: SchemaField[],
  inputDefaults: Record<string, unknown> | null,
): SheetRow {
  const r: SheetRow = {}
  for (const f of fields) {
    r[fieldKey(f)] = ''
  }
  if (inputDefaults) {
    for (const f of fields) {
      const fk = fieldKey(f)
      if (isSerial(f)) continue
      const v = formFieldDefault(inputDefaults, f)
      if (Array.isArray(v)) {
        if (v.length) r[fk] = v.join(',')
      } else if (String(v).trim()) {
        if (String(f.ftype).toUpperCase() === 'DATETIME') {
          r[fk] = formatDateTimeDisplay(v, dateTimeKind(f)) || v
        } else {
          r[fk] = v
        }
      }
    }
  }
  return r
}

export function newRowWithCode(
  code: string,
  fields: SchemaField[],
  inputDefaults: Record<string, unknown> | null,
): SheetRow {
  const r = emptyRow(fields, inputDefaults)
  if (code) {
    r.uukey = code
    const ukField = fields.find((f) => isSerial(f))
    if (ukField) r[fieldKey(ukField)] = code
  }
  return r
}

export function rowsToMatrix(list: SheetRow[], fields: SchemaField[]): string[][] {
  return list.map((row) => fields.map((f) => row[fieldKey(f)] ?? ''))
}

export function matrixToRows(
  data: unknown[][],
  fields: SchemaField[],
  referCache: ReferDict,
): SheetRow[] {
  return data.map((line) => {
    const r: SheetRow = {}
    fields.forEach((f, i) => {
      let v = line[i] == null ? '' : String(line[i])
      if (isDropdownField(f)) v = normalizeDropdownCellValue(f, v, referCache)
      r[fieldKey(f)] = v
    })
    syncRowUUKey(r, fields)
    return r
  })
}
