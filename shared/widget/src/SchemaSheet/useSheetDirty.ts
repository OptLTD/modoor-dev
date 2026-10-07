import { ref, type Ref } from 'vue'
import type { SchemaField } from '@modoor/hooks'
import type { SheetRow, SheetWorksheet } from './types'
import { normalizeDropdownCellValue } from './dropdown'
import {type ReferDict, dateTimeKind } from '@modoor/hooks'
import { isDropdownField, isNumeric } from './fieldUtils'
import { fieldKey, formatDateTimeDisplay } from '@modoor/hooks'

export function useSheetDirty(
  getWorksheet: () => SheetWorksheet | null,
  getFields: () => SchemaField[],
  getReferCache: () => ReferDict,
) {
  const originRows = ref<SheetRow[]>([])
  const dirtyCells = new Set<string>()

  function cellDirtyKey(row: number, col: number) {
    return `${row},${col}`
  }

  function originValueAt(row: number, col: number): string {
    const f = getFields()[col]
    if (!f) return ''
    return originRows.value[row]?.[fieldKey(f)] ?? ''
  }

  function canonicalCellValue(f: SchemaField, val: string): string {
    const s = String(val ?? '').trim()
    if (!s) return ''
    if (isDropdownField(f)) {
      return normalizeDropdownCellValue(f, s, getReferCache())
    }
    if (isNumeric(f)) {
      const n = Number(s)
      if (Number.isFinite(n)) return String(n)
    }
    // 与 sheet calendar 展示格式对齐，避免 ISO/时区后缀误判 dirty
    if (String(f.ftype).toUpperCase() === 'DATETIME') {
      return formatDateTimeDisplay(s, dateTimeKind(f)) || s
    }
    return s
  }

  function isCellValueDirty(row: number, col: number, current: string): boolean {
    const f = getFields()[col]
    if (!f) return false
    const origin = originValueAt(row, col)
    return (
      canonicalCellValue(f, current) !== canonicalCellValue(f, origin)
    )
  }

  function resolveCellElement(row: number, col: number, cellEl?: HTMLElement | null) {
    if (cellEl?.isConnected) return cellEl
    const worksheet = getWorksheet()
    if (!worksheet) return null
    if (typeof worksheet.getCellFromCoords === 'function') {
      return (worksheet.getCellFromCoords(col, row) as HTMLElement | undefined) ?? null
    }
    if (typeof worksheet.getCell === 'function') {
      return (worksheet.getCell(col, row) as HTMLElement | undefined) ?? null
    }
    return null
  }

  function syncDirtyCellClass(
    row: number,
    col: number,
    dirty: boolean,
    cellEl?: HTMLElement | null,
  ) {
    const cell = resolveCellElement(row, col, cellEl)
    if (!cell) return
    cell.classList.toggle('sheet-cell-dirty', dirty)
  }

  function markCellDirty(
    row: number,
    col: number,
    current: string,
    cellEl?: HTMLElement | null,
  ) {
    const key = cellDirtyKey(row, col)
    const dirty = isCellValueDirty(row, col, current)
    if (dirty) dirtyCells.add(key)
    else dirtyCells.delete(key)
    syncDirtyCellClass(row, col, dirty, cellEl)
  }

  function resetSheetState(list: SheetRow[]) {
    originRows.value = list.map((r) => ({ ...r }))
    dirtyCells.clear()
  }

  /** 与 sheet insertRow 同步：在 index 处插入空白/初始 origin，避免行错位导致 dirty 反转 */
  function insertOriginRows(index: number, rows: SheetRow[]) {
    if (!rows.length) return
    const copies = rows.map((r) => ({ ...r }))
    originRows.value.splice(Math.max(0, index), 0, ...copies)
  }

  function syncAllDirtyClasses() {
    const worksheet = getWorksheet()
    if (!worksheet?.getData) return
    const data = worksheet.getData(false, true) as unknown[][]
    const fields = getFields()
    for (let r = 0; r < data.length; r++) {
      for (let c = 0; c < fields.length; c++) {
        const v = data[r][c] == null ? '' : String(data[r][c])
        markCellDirty(r, c, v)
      }
    }
  }

  function isRowDirty(row: number): boolean {
    const fields = getFields()
    for (let c = 0; c < fields.length; c++) {
      if (dirtyCells.has(cellDirtyKey(row, c))) return true
    }
    return false
  }

  /** 有任意脏单元格的行号（升序） */
  function dirtyRowIndices(): number[] {
    const idxs = new Set<number>()
    for (const key of dirtyCells) {
      const row = Number(String(key).split(',')[0])
      if (Number.isFinite(row) && row >= 0) idxs.add(row)
    }
    return [...idxs].sort((a, b) => a - b)
  }

  return {
    originRows: originRows as Ref<SheetRow[]>,
    markCellDirty,
    resetSheetState,
    insertOriginRows,
    syncAllDirtyClasses,
    isRowDirty,
    dirtyRowIndices,
  }
}
