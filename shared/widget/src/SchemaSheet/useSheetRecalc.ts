import type { Ref } from 'vue'
import type { RecordGateway, SchemaField } from '@modoor/hooks'
import { fieldKey, rowToUpsertPayload } from '@modoor/hooks'
import { shouldSyncAutofillColumn } from './sheetFormula'
import type { RecalcPending, SheetWorksheet } from './types'
import { requiredTips, setRequiredComment } from './fieldUtils'

const RECALC_DEBOUNCE_MS = 280
const PASTE_BURST_IDLE_MS = 160
const AUTOFILL_CHUNK = 100

export type SheetRecalcDeps = {
  getWorksheet: () => SheetWorksheet | null
  getFields: () => SchemaField[]
  getDependsTriggers: () => string[]
  model: () => string
  using: () => string
  error: Ref<string>
  markCellDirty: (row: number, col: number, current: string) => void
  readSheetRows: () => Record<string, string>[]
  syncAllDirtyClasses: () => void
  gateway: RecordGateway
}

export function useSheetRecalc(deps: SheetRecalcDeps) {
  let recalcApplyDepth = 0
  /** 程序写回后 jspreadsheet 可能延迟触发 onchange，需跨 macrotask 抑制 scheduleRecalc */
  let recalcSuppressCount = 0
  let recalcInFlight = false
  let pasteBurstActive = false
  let recalcFlushTimer: ReturnType<typeof setTimeout> | null = null
  let pasteBurstTimer: ReturnType<typeof setTimeout> | null = null
  const recalcPendingByCell = new Map<string, RecalcPending>()
  const recalcBurstByRow = new Map<number, number>()
  const MAX_RECALC_BURST = 12

  function cellDirtyKey(row: number, col: number) {
    return `${row},${col}`
  }

  function beginRecalcSuppress() {
    recalcSuppressCount++
  }

  function endRecalcSuppress() {
    setTimeout(() => {
      recalcSuppressCount = Math.max(0, recalcSuppressCount - 1)
    }, 0)
  }

  function applyAutofillResultInner(
    row: number,
    triggerUukey: string,
    flat: Record<string, unknown>,
  ) {
    const worksheet = deps.getWorksheet()
    if (!worksheet) return
    const fields = deps.getFields()
    const dirtyUpdates: { row: number; col: number; str: string; f: (typeof fields)[number] }[] = []
    for (let j = 0; j < fields.length; j++) {
      const f = fields[j]
      if (!shouldSyncAutofillColumn(f, triggerUukey)) continue
      const uk = fieldKey(f)
      const raw = flat[uk] ?? flat[f.uukey]
      const str = raw == null ? '' : String(raw)
      worksheet.setValueFromCoords(j, row, str, true)
      dirtyUpdates.push({ row, col: j, str, f })
    }
    queueMicrotask(() => {
      for (const u of dirtyUpdates) {
        deps.markCellDirty(u.row, u.col, u.str)
        setRequiredComment(worksheet, u.col, u.row, requiredTips(u.f, u.str))
      }
    })
  }

  function applyAutofillResult(row: number, triggerUukey: string, flat: Record<string, unknown>) {
    beginRecalcSuppress()
    recalcApplyDepth++
    try {
      applyAutofillResultInner(row, triggerUukey, flat)
    } finally {
      recalcApplyDepth = Math.max(0, recalcApplyDepth - 1)
      endRecalcSuppress()
    }
    recalcBurstByRow.delete(row)
  }

  async function recalcRow(row: number, triggerUukey: string) {
    const rows = deps.readSheetRows()
    const rowData = rows[row]
    if (!rowData) return
    const payload = rowToUpsertPayload(rowData, deps.getFields())
    const using = deps.using() === 'sheet' ? 'default' : deps.using()
    try {
      const resp = await deps.gateway.autofillRecord(deps.model(), payload, using)
      applyAutofillResult(row, triggerUukey, resp.data)
    } catch (e: unknown) {
      deps.error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function scheduleRecalc(row: number, col: number, triggerUukey: string) {
    if (recalcApplyDepth > 0 || recalcSuppressCount > 0) return
    const burst = (recalcBurstByRow.get(row) ?? 0) + 1
    if (burst > MAX_RECALC_BURST) return
    recalcBurstByRow.set(row, burst)
    recalcPendingByCell.set(cellDirtyKey(row, col), { row, col, triggerUukey })
    if (recalcFlushTimer != null) clearTimeout(recalcFlushTimer)
    recalcFlushTimer = setTimeout(flushPendingRecalc, RECALC_DEBOUNCE_MS)
  }

  async function flushPendingRecalc() {
    recalcFlushTimer = null
    if (recalcPendingByCell.size === 0 || recalcInFlight) return
    recalcInFlight = true
    const snapshot = [...recalcPendingByCell.values()]
    recalcPendingByCell.clear()
    const byRow = new Map<number, RecalcPending>()
    for (const p of snapshot) byRow.set(p.row, p)
    try {
      for (const pending of byRow.values()) {
        await recalcRow(pending.row, pending.triggerUukey)
      }
    } finally {
      recalcInFlight = false
    }
  }

  async function flushBulkRecalc(items: { row: number; triggerUukey: string }[]) {
    if (!items.length) return
    const rows = deps.readSheetRows()
    const using = deps.using() === 'sheet' ? 'default' : deps.using()
    for (let off = 0; off < items.length; off += AUTOFILL_CHUNK) {
      const chunk = items.slice(off, off + AUTOFILL_CHUNK)
      const batch = chunk.map(({ row }) => rowToUpsertPayload(rows[row], deps.getFields()))
      try {
        const resp = await deps.gateway.autofillBatch(deps.model(), batch, using)
        const flats = resp.data
        if (!Array.isArray(flats) || flats.length !== chunk.length) {
          deps.error.value = '自动填充返回异常'
          return
        }
        beginRecalcSuppress()
        recalcApplyDepth++
        try {
          chunk.forEach((item, i) => {
            applyAutofillResultInner(item.row, item.triggerUukey, flats[i])
          })
        } finally {
          recalcApplyDepth = Math.max(0, recalcApplyDepth - 1)
          endRecalcSuppress()
        }
      } catch (e: unknown) {
        deps.error.value = e instanceof Error ? e.message : String(e)
        return
      }
    }
  }

  function emitConsolidatedBulkRecalc() {
    const triggers = deps.getDependsTriggers()
    const worksheet = deps.getWorksheet()
    if (!triggers.length || !worksheet) return
    const fields = deps.getFields()
    let anchorCol = -1
    for (let c = 0; c < fields.length; c++) {
      const uk = fieldKey(fields[c])
      if (triggers.includes(uk)) {
        anchorCol = c
        break
      }
    }
    if (anchorCol < 0) return
    const rows = deps.readSheetRows()
    const triggerUukey = fieldKey(fields[anchorCol])
    const items = rows.map((_, r) => ({ row: r, triggerUukey }))
    void flushBulkRecalc(items)
  }

  function schedulePasteBurstEnd() {
    pasteBurstActive = true
    if (pasteBurstTimer != null) clearTimeout(pasteBurstTimer)
    pasteBurstTimer = setTimeout(finishPasteBurst, PASTE_BURST_IDLE_MS)
  }

  function finishPasteBurst() {
    pasteBurstTimer = null
    pasteBurstActive = false
    if (recalcFlushTimer != null) {
      clearTimeout(recalcFlushTimer)
      recalcFlushTimer = null
    }
    recalcPendingByCell.clear()
    emitConsolidatedBulkRecalc()
    deps.syncAllDirtyClasses()
  }

  function isPasteBurstActive() {
    return pasteBurstActive
  }

  function isRecalcApplying() {
    return recalcApplyDepth > 0 || recalcSuppressCount > 0
  }

  function dispose() {
    if (recalcFlushTimer != null) clearTimeout(recalcFlushTimer)
    if (pasteBurstTimer != null) clearTimeout(pasteBurstTimer)
  }

  return {
    scheduleRecalc,
    schedulePasteBurstEnd,
    isPasteBurstActive,
    isRecalcApplying,
    dispose,
  }
}
