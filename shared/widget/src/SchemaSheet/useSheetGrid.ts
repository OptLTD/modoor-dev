import { ref, type Ref } from 'vue'
import jspreadsheet from 'jspreadsheet-ce'
import type { RecordGateway, ReferDict, SchemaField } from '@modoor/hooks'
import { fieldKey } from '@modoor/hooks'
import type { SheetRow, SheetWorksheet } from './types'
import {
  columnTitle,
  isDropdownField,
  isNumeric,
  isSerial,
  isSheetReadOnly,
  canTriggerRecalc,
  requiredTips,
  setRequiredComment,
} from './fieldUtils'
import {
  dropdownExcelText,
  dropdownSource,
  normalizeDropdownCellValue,
} from './dropdown'
import { loadColWidths, resolveColWidth, saveColWidth } from './colWidth'
import { dateTimeKind, isOnlyDate } from '@modoor/hooks'

type OverflowSnapshot = {
  el: HTMLElement
  overflow: string
  overflowX: string
  overflowY: string
  scrollLeft: number
  scrollTop: number
}

let overflowSnapshots: OverflowSnapshot[] = []

function restoreSheetOverflow() {
  for (const s of overflowSnapshots) {
    s.el.style.overflow = s.overflow
    s.el.style.overflowX = s.overflowX
    s.el.style.overflowY = s.overflowY
    s.el.scrollLeft = s.scrollLeft
    s.el.scrollTop = s.scrollTop
  }
  overflowSnapshots = []
}

/**
 * 打开日历时只放开外层 .sheet-scroll 的裁切。
 * 切勿把 .jss_content 的 overflow 改成 visible：浏览器会把 scrollLeft 清零，导致横向滚动抖动。
 * jcalendar 挂到 body 下会导致组件不生效。
 * 日历已 position:fixed，配合临时 overflow:visible 避免被裁切。
 */
function unclipSheetForCalendar(input: HTMLElement) {
  restoreSheetOverflow()
  const el = input.closest('.sheet-scroll') as HTMLElement | null
  if (!el) return
  overflowSnapshots.push({
    el,
    overflow: el.style.overflow,
    overflowX: el.style.overflowX,
    overflowY: el.style.overflowY,
    scrollLeft: el.scrollLeft,
    scrollTop: el.scrollTop,
  })
  el.style.overflow = 'visible'
  el.style.overflowX = 'visible'
  el.style.overflowY = 'visible'
}

function jSuitesState(): unknown[] {
  const w = window as Window & { jSuitesStateControl?: unknown[] }
  if (!Array.isArray(w.jSuitesStateControl)) w.jSuitesStateControl = []
  return w.jSuitesStateControl
}

/** 时分用原生 select，点选项会被 jSuites 全局 mousedown 当成“点外面”而 close */
function guardCalendarTimeSelects(input: HTMLElement) {
  const cal =
    (input.parentElement?.querySelector(':scope > .jcalendar') as HTMLElement | null) ||
    (input.nextElementSibling instanceof HTMLElement &&
    input.nextElementSibling.classList.contains('jcalendar')
      ? input.nextElementSibling
      : null)
  if (!cal) return
  const obj = (input as HTMLElement & { calendar?: unknown }).calendar
  if (!obj) return

  cal.querySelectorAll('select').forEach((sel) => {
    sel.addEventListener('mousedown', (e) => e.stopPropagation())
    sel.addEventListener('mouseup', (e) => e.stopPropagation())
    sel.addEventListener('focus', () => {
      const state = jSuitesState()
      const i = state.indexOf(obj)
      if (i >= 0) state.splice(i, 1)
    })
    sel.addEventListener('blur', () => {
      const state = jSuitesState()
      if (!state.includes(obj)) state.push(obj)
    })
  })
}

function sheetCalendarOptions(onlyDate: boolean) {
  return {
    format: onlyDate ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH24:MI',
    ...(onlyDate ? {} : { time: true as const }),
    // tableOverflow 时库也会设 position；显式保留 fixed，配合临时 overflow:visible
    position: true as const,
    onopen(el: HTMLElement) {
      unclipSheetForCalendar(el)
      if (!onlyDate) guardCalendarTimeSelects(el)
    },
  }
}

export type SheetGridDeps = {
  model: () => string
  using: () => string
  colWidths: Record<string, number>
  getFields: () => SchemaField[]
  getFreezeColumns: () => number
  getReferCache: () => ReferDict
  getDependsTriggers: () => string[]
  markCellDirty: (row: number, col: number, current: string, cellEl?: HTMLElement | null) => void
  insertOriginRows: (index: number, rows: SheetRow[]) => void
  scheduleRecalc: (row: number, col: number, triggerUukey: string) => void
  schedulePasteBurstEnd: () => void
  isPasteBurstActive: () => boolean
  isRecalcApplying: () => boolean
  onSelection: (idxs: number[]) => void
  getAutoHeight?: () => boolean
  gateway: RecordGateway
}

export function useSheetGrid(deps: SheetGridDeps) {
  const host = ref<HTMLDivElement | null>(null)
  let worksheet: SheetWorksheet | null = null
  let resizeObs: ResizeObserver | null = null

  function getWorksheet() {
    return worksheet
  }

  const HEADER_H = 34
  const ROW_H = 28

  function sheetRowCount(): number {
    try {
      const data =
        typeof worksheet?.getData === 'function'
          ? (worksheet.getData(false, true) as unknown[][])
          : []
      return Math.max(Array.isArray(data) ? data.length : 1, 1)
    } catch {
      return 1
    }
  }

  function autoContentHeight(): number {
    return HEADER_H + sheetRowCount() * ROW_H + 4
  }

  function syncGridLayout() {
    const el = host.value
    if (!el || !worksheet?.content) return
    const auto = Boolean(deps.getAutoHeight?.())
    // 页签隐藏时尺寸为 0，勿把表格钉死在兜底宽高
    if (!auto && (el.clientWidth < 80 || el.clientHeight < 80)) return
    const content = worksheet.content as HTMLElement
    const w = Math.max(el.clientWidth, 480)
    const h = auto ? autoContentHeight() : el.clientHeight
    if (auto) {
      el.style.height = `${h}px`
    }
    content.style.width = `${w}px`
    // Wails/WebKit 仅设 maxHeight 时内容会按表格 intrinsic 高度收缩，需同时钉死 height
    content.style.height = `${h}px`
    content.style.maxHeight = `${h}px`
    // 日历打开期间不要强行改 overflow，避免与 unclip 打架
    if (overflowSnapshots.length === 0) {
      content.style.overflowX = 'auto'
      content.style.overflowY = auto ? 'hidden' : 'auto'
    }
  }

  function buildColumns(rows: SheetRow[] = []): any[] {
    const referCache = deps.getReferCache()
    return deps.getFields().map((f) => {
      const title = columnTitle(f)
      const width = resolveColWidth(f, deps.colWidths)
      const readOnly = isSheetReadOnly(f)
      if (isSerial(f)) {
        return { type: 'text' as const, title, width, readOnly: true, align: 'center' }
      }
      if (isDropdownField(f)) {
        const fk = fieldKey(f)
        const extras = rows.map((row) => row[fk]).filter((v) => String(v).trim())
        return {
          type: 'dropdown' as const,
          title,
          width,
          readOnly,
          source: dropdownSource(f, referCache, extras),
          autocomplete: true,
        }
      }
      if (isNumeric(f)) {
        return { type: 'numeric' as const, title, width, readOnly, align: 'right' }
      }
      if (String(f.ftype).toUpperCase() === 'DATETIME') {
        const kind = dateTimeKind(f)
        // jsuites calendar 无 month 模式；ONLYMONTH 用文本 + YYYY-MM 展示
        if (kind === 'ONLYMONTH') {
          return { type: 'text' as const, title, width, readOnly }
        }
        const onlyDate = kind === 'ONLYDATE' || isOnlyDate(f)
        return {
          type: 'calendar' as const,
          title,
          width,
          readOnly,
          options: sheetCalendarOptions(onlyDate),
        }
      }
      return { type: 'text' as const, title, width, readOnly }
    })
  }

  function onBeforeChange(
    _instance: unknown,
    _cell: HTMLTableCellElement,
    colIndex: string | number,
    _rowIndex: string | number,
    newValue: unknown,
  ) {
    const f = deps.getFields()[Number(colIndex)]
    if (!f || !isDropdownField(f)) return undefined
    return normalizeDropdownCellValue(f, String(newValue ?? ''), deps.getReferCache())
  }

  function onCellChange(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    instance: any,
    _cell: HTMLTableCellElement,
    colIndex: string | number,
    rowIndex: string | number,
    value: unknown,
  ) {
    const col = Number(colIndex)
    const row = Number(rowIndex)
    const f = deps.getFields()[col]
    if (!f) return
    const strVal = value == null ? '' : String(value)
    const fk = fieldKey(f)
    const applying = deps.isRecalcApplying()
    const pasting = deps.isPasteBurstActive()
    const shouldRecalc = !applying && !pasting && canTriggerRecalc(f, deps.getDependsTriggers())

    if (applying || pasting) {
      deps.markCellDirty(row, col, strVal, _cell)
      return
    }

    if (shouldRecalc) {
      deps.scheduleRecalc(row, col, fk)
    }

    const cellEl = _cell
    // 避免在 jspreadsheet onchange 回调内同步 setComments 导致重入卡死
    queueMicrotask(() => {
      // 先标 dirty：setComments 在部分列会抛错，若放前面会导致 dirty 永远不跑
      deps.markCellDirty(row, col, strVal, cellEl)
      if (deps.isRecalcApplying()) return
      setRequiredComment(instance, col, row, requiredTips(f, strVal))
    })
  }

  function onBeforePaste(
    _instance: unknown,
    copiedText: { value: unknown }[][],
    colIndex: number | string,
    rowIndex: number | string,
  ): boolean | undefined {
    if (!worksheet || typeof worksheet.setValueFromCoords !== 'function') return undefined

    const startCol = Number(colIndex)
    const startRow = Number(rowIndex)
    const fields = deps.getFields()
    const referCache = deps.getReferCache()
    const data =
      typeof worksheet.getData === 'function'
        ? (worksheet.getData(false, true) as unknown[][])
        : []
    const needRows = startRow + copiedText.length
    const addCount = needRows > data.length ? needRows - data.length : 0
    if (addCount > 0 && typeof worksheet.insertRow === 'function') {
      worksheet.insertRow(addCount)
      // 末尾追加的空行：origin 同步为空，避免与旧行错位
      deps.insertOriginRows(
        data.length,
        Array.from({ length: addCount }, () => ({})),
      )
    }

    let maxCols = 0
    for (let ri = 0; ri < copiedText.length; ri++) {
      maxCols = Math.max(maxCols, copiedText[ri]?.length || 0)
      for (let ci = 0; ci < copiedText[ri].length; ci++) {
        const sheetCol = startCol + ci
        const f = fields[sheetCol]
        if (!f) continue
        let v = String(copiedText[ri][ci]?.value ?? '')
          .replace(/\r/g, '')
          .trim()
        if (isDropdownField(f)) v = normalizeDropdownCellValue(f, v, referCache)
        worksheet.setValueFromCoords(sheetCol, startRow + ri, v, true)
      }
    }
    // onbeforepaste 返回 false 会跳过库内 selection.AH，需手动框选粘贴区域
    const endRow = startRow + Math.max(copiedText.length, 1) - 1
    const endCol = startCol + Math.max(maxCols, 1) - 1
    if (typeof worksheet.updateSelectionFromCoords === 'function') {
      worksheet.updateSelectionFromCoords(startCol, startRow, endCol, endRow)
    }
    deps.schedulePasteBurstEnd()
    if (deps.getAutoHeight?.()) queueMicrotask(() => syncGridLayout())
    return false
  }

  function onCopy(
    _instance: unknown,
    selectedRange: [number, number, number, number],
    copiedData: string,
  ) {
    const left = Math.min(selectedRange[0], selectedRange[2])
    const fields = deps.getFields()
    const referCache = deps.getReferCache()
    const lines = copiedData.split(/\r?\n/)
    return lines
      .map((line) => {
        const cells = line.split('\t')
        return cells
          .map((cell, ci) => {
            const f = fields[left + ci]
            if (!f || !isDropdownField(f)) return cell
            return dropdownExcelText(f, cell, referCache)
          })
          .join('\t')
      })
      .join('\n')
  }

  function onResizeColumn(_instance: unknown, colIndex: number | number[], newWidth: number | number[]) {
    const idxs = Array.isArray(colIndex) ? colIndex : [colIndex]
    const widths = Array.isArray(newWidth) ? newWidth : [newWidth]
    const fields = deps.getFields()
    idxs.forEach((idx, i) => {
      const f = fields[idx]
      const w = widths[i]
      if (!f?.field || !Number.isFinite(Number(w))) return
      saveColWidth(deps.model(), deps.using(), fieldKey(f), Number(w), deps.colWidths, deps.gateway)
    })
  }

  function handleSelection(_instance: unknown, _x1: number, y1: number, _x2: number, y2: number) {
    try {
      const top = Math.min(y1, y2)
      const bottom = Math.max(y1, y2)
      const idxs: number[] = []
      for (let i = top; i <= bottom; i++) idxs.push(i)
      deps.onSelection(idxs)
    } catch {
      deps.onSelection([])
    }
  }

  function destroyGrid() {
    resizeObs?.disconnect()
    resizeObs = null
    restoreSheetOverflow()
    if (!host.value) return
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      jspreadsheet.destroy(host.value as any)
    } catch {
      /* ignore */
    }
    worksheet = null
    if (host.value) host.value.innerHTML = ''
  }

  async function mountGrid(data: string[][], rows: SheetRow[] = []) {
    if (!host.value) return
    const fields = deps.getFields()
    if (!fields.length) return
    destroyGrid()
    await loadColWidths(deps.model(), deps.using(), fields, deps.colWidths, deps.gateway)
    if (!host.value) return
    const cols = fields.length
    const w = Math.max(host.value.clientWidth || 0, 480)
    const rowCount = Math.max(data.length, 1)
    const auto = Boolean(deps.getAutoHeight?.())
    const h = auto
      ? HEADER_H + rowCount * ROW_H + 4
      : Math.max(host.value.clientHeight || 0, 200)
    const instance = jspreadsheet(host.value, {
      autoIncrement: false,
      onselection: handleSelection,
      onresizecolumn: onResizeColumn,
      onbeforechange: onBeforeChange,
      onbeforepaste: onBeforePaste as never,
      oncopy: onCopy,
      onchange: onCellChange,
      oneditionend: () => {
        queueMicrotask(() => restoreSheetOverflow())
      },
      worksheets: [
        {
          data: data.length ? data : [Array.from({ length: cols }, () => '')],
          columns: buildColumns(rows),
          freezeColumns: deps.getFreezeColumns(),
          tableOverflow: true,
          tableWidth: `${w}px`,
          tableHeight: `${h}px`,
          allowInsertRow: true,
          allowDeleteRow: true,
          allowInsertColumn: false,
          allowDeleteColumn: false,
          columnSorting: false,
          columnResize: true,
          minDimensions: [cols, rowCount] as [number, number],
        },
      ],
    })
    worksheet = Array.isArray(instance) ? instance[0] : instance
    syncGridLayout()
    if (host.value) {
      resizeObs?.disconnect()
      resizeObs = new ResizeObserver(() => syncGridLayout())
      resizeObs.observe(host.value)
    }
    deps.onSelection([])
  }

  return {
    host: host as Ref<HTMLDivElement | null>,
    getWorksheet,
    mountGrid,
    destroyGrid,
    syncGridLayout,
  }
}
