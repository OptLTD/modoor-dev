import jspreadsheet from 'jspreadsheet-ce'
import type { SchemaField } from '@modoor/hooks'
import { dateTimeKind, editableMode, isRequired } from '@modoor/hooks'
import { fieldKey } from '@modoor/hooks'
import { extraHasFormula } from './sheetFormula'
import type { SheetRow, SheetWorksheet } from './types'

export function isRelation(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'RELATION'
}

export function isNumeric(f: SchemaField) {
  const t = String(f.ftype).toUpperCase()
  return t === 'NUMERIC' || t === 'EXPENSE' || t === 'INTEGER'
}

export function isSerial(f: SchemaField) {
  return f.field === 'uukey' || String(f.ftype).toUpperCase() === 'SERIALNO'
}

export function isDropdownField(f: SchemaField) {
  const t = String(f.ftype).toUpperCase()
  return t === 'RELATION' || t === 'OPTIONAL' || t === 'WORKFLOW'
}

export function requiredTips(f: SchemaField, val: unknown): string {
  if (!isRequired(f)) return ''
  const s = val == null ? '' : String(val).trim()
  if (!s) return `${f.label || f.field} 为必填项`
  return ''
}

/** 校验待保存行必填；有空必填则返回提示文案，通过则 null */
export function validateRequiredRows(rows: SheetRow[], fields: SchemaField[]): string | null {
  for (const row of rows) {
    for (const f of fields) {
      if (isSerial(f)) continue
      if (requiredTips(f, row[fieldKey(f)])) return '请完善必填字段'
    }
  }
  return null
}

/** 用 A1 坐标设置/清除必填 comment（jspreadsheet-ce 不接受 [col,row]） */
export function setRequiredComment(
  worksheet: SheetWorksheet,
  col: number,
  row: number,
  tip: string,
) {
  if (!worksheet || typeof worksheet.setComments !== 'function') return
  try {
    const cell = jspreadsheet.helpers.getCellNameFromCoords(col, row)
    worksheet.setComments(cell, tip || '')
  } catch {
    /* ignore comment errors */
  }
}

/** 扫描空必填格并写入 jss_comments；rowFilter 可限定新增行 */
export function syncRequiredComments(
  worksheet: SheetWorksheet,
  fields: SchemaField[],
  rowFilter?: (row: number) => boolean,
) {
  if (!worksheet || typeof worksheet.getData !== 'function') return
  if (!fields.length) return
  const data = worksheet.getData(false, true) as unknown[][]
  if (!Array.isArray(data)) return
  for (let r = 0; r < data.length; r++) {
    if (rowFilter && !rowFilter(r)) continue
    const row = data[r] || []
    for (let c = 0; c < fields.length; c++) {
      const tip = requiredTips(fields[c], row[c])
      setRequiredComment(worksheet, c, r, tip)
    }
  }
}

export function columnTitle(f: SchemaField) {
  const label = f.label || f.field
  return isRequired(f) ? `*${label}` : label
}

export function isSheetReadOnly(f: SchemaField) {
  if (isSerial(f)) return true
  if (editableMode(f) === 'NEVER') return true
  if (extraHasFormula(f.extra)) return true
  return false
}

export function canTriggerRecalc(f: SchemaField, dependsTriggers: string[]) {
  if (isSheetReadOnly(f)) return false
  if (extraHasFormula(f.extra)) return false
  const key = fieldKey(f)
  return !!key && dependsTriggers.includes(key)
}

export function defaultColWidth(f: SchemaField) {
  if (isSerial(f)) return 120
  if (isRelation(f)) return 140
  if (String(f.ftype).toUpperCase() === 'OPTIONAL') return 120
  if (isNumeric(f)) return 110
  if (String(f.ftype).toUpperCase() === 'DATETIME') {
    const kind = dateTimeKind(f)
    if (kind === 'ONLYMONTH' || kind === 'ONLYDATE') return 130
    return 160
  }
  return Math.max(80, Number(f.width) || 140)
}
