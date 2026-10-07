import { computed, nextTick, onBeforeUnmount, reactive, ref, toRefs, watch, type ToRefs } from 'vue'
import { useRecordGateway } from '@modoor/hooks'
import { isSerial, syncRequiredComments, validateRequiredRows } from './fieldUtils'
import { exportRows } from '@modoor/hooks'
import { buildDependsTriggers } from './sheetFormula'
import { appAlert, appConfirm, appToast } from '@modoor/hooks'
import { applyStickyOrder, normalizeReferDict, type ReferDict } from '@modoor/hooks'
import { fieldKey, rowToUpsertPayload, rowUUKey } from '@modoor/hooks'
import type { SchemaSheetProps, SheetRow, SheetWorksheet } from './types'
import {
  fromSearchRow,
  isSheetRowEmpty,
  matrixToRows,
  newRowWithCode,
  rowsToMatrix,
  syncRowUUKey,
} from './rowMapper'
import { useSheetDirty } from './useSheetDirty'
import { useSheetRecalc } from './useSheetRecalc'
import { useSheetGrid } from './useSheetGrid'

function isStickyFieldFn(f: { uukey: string; field: string }, stickyKeys: string[]) {
  return stickyKeys.includes(f.uukey) || stickyKeys.includes(`basic.${f.field}`)
}

export function useSchemaSheet(props: ToRefs<SchemaSheetProps>) {
  const gateway = useRecordGateway()
  const error = ref('')
  const saving = ref(false)
  const message = ref('')
  const loading = ref(false)
  const count = ref(0)
  const selectedIndices = ref<number[]>([])
  const lastSelectedIndices = ref<number[]>([])
  const colWidths = reactive<Record<string, number>>({})
  const inputDefaults = ref<Record<string, unknown> | null>(null)
  const referCache = ref<ReferDict>({})

  let reloadSeq = 0
  // 不能用已完成的 Promise：watch 会先 await 默认值请求，reload 才挂上表格。
  let ready: Promise<void> = new Promise(() => {})

  const table = computed(() => props.table.value)
  const request = computed(() => props.request?.value)
  const mode = computed(() => props.mode?.value || 'modify')

  const stickyKeys = computed(() => {
    const sticky = table.value.sticky
    const keys = sticky?.length ? [...sticky] : ['basic.uukey']
    return keys.filter((k) =>
      table.value.fields.some((f) => f.uukey === k || `basic.${f.field}` === k),
    )
  })

  const editableFields = computed(() => {
    const all = table.value.fields.filter(
      (f) => f.field && f.field !== 'model' && f.shown !== false,
    )
    const keys = applyStickyOrder(
      all.map((f) => f.uukey),
      stickyKeys.value,
    )
    const byKey = new Map(all.map((f) => [f.uukey, f]))
    return keys.map((k) => byKey.get(k)).filter(Boolean) as typeof table.value.fields
  })

  const freezeColumns = computed(() => {
    let n = 0
    for (const f of editableFields.value) {
      if (!isStickyFieldFn(f, stickyKeys.value)) break
      n += 1
    }
    return n
  })

  const dependsTriggers = computed(() => buildDependsTriggers(editableFields.value))

  function syncSelection(idxs: number[]) {
    selectedIndices.value = idxs
    if (idxs.length) lastSelectedIndices.value = [...idxs]
  }

  function clearSelection() {
    selectedIndices.value = []
    lastSelectedIndices.value = []
  }

  function resolveSelectedIndices(): number[] {
    if (selectedIndices.value.length) return [...selectedIndices.value]
    if (lastSelectedIndices.value.length) return [...lastSelectedIndices.value]
    const worksheet = getWorksheet()
    if (worksheet && typeof worksheet.getSelectedRows === 'function') {
      const idxs = worksheet.getSelectedRows(true) as number[]
      if (Array.isArray(idxs) && idxs.length) return [...idxs]
    }
    return []
  }

  let getWorksheet: () => SheetWorksheet | null = () => null
  let dirty!: ReturnType<typeof useSheetDirty>
  let recalc!: ReturnType<typeof useSheetRecalc>
  let grid!: ReturnType<typeof useSheetGrid>

  function readSheetRows(): SheetRow[] {
    const worksheet = getWorksheet()
    if (!worksheet?.getData) return []
    const data = worksheet.getData(false, true) as unknown[][]
    return matrixToRows(data || [], editableFields.value, referCache.value)
  }

  dirty = useSheetDirty(() => getWorksheet(), () => editableFields.value, () => referCache.value)

  recalc = useSheetRecalc({
    getWorksheet: () => getWorksheet(),
    getFields: () => editableFields.value,
    getDependsTriggers: () => dependsTriggers.value,
    model: () => table.value.model,
    using: () => table.value.using || 'default',
    error,
    markCellDirty: dirty.markCellDirty,
    readSheetRows,
    syncAllDirtyClasses: dirty.syncAllDirtyClasses,
    gateway,
  })

  grid = useSheetGrid({
    model: () => table.value.model,
    using: () => table.value.using || 'default',
    colWidths,
    getFields: () => editableFields.value,
    getFreezeColumns: () => freezeColumns.value,
    getReferCache: () => referCache.value,
    getDependsTriggers: () => dependsTriggers.value,
    markCellDirty: dirty.markCellDirty,
    insertOriginRows: dirty.insertOriginRows,
    scheduleRecalc: recalc.scheduleRecalc,
    schedulePasteBurstEnd: recalc.schedulePasteBurstEnd,
    isPasteBurstActive: recalc.isPasteBurstActive,
    isRecalcApplying: recalc.isRecalcApplying,
    onSelection: syncSelection,
    getAutoHeight: () => Boolean(props.autoHeight?.value),
    gateway,
  })
  getWorksheet = grid.getWorksheet

  async function waitForHost(maxFrames = 12): Promise<boolean> {
    for (let i = 0; i < maxFrames; i++) {
      await nextTick()
      await new Promise<void>((r) => requestAnimationFrame(() => r()))
      const el = grid.host.value
      if (el?.isConnected) return true
    }
    return !!grid.host.value?.isConnected
  }

  async function loadInputDefaults() {
    try {
      const res = await gateway.fetchInputSchema(table.value.model, table.value.using || 'default', 'INSERT')
      inputDefaults.value = res.input?.values ?? null
    } catch {
      inputDefaults.value = null
    }
  }

  async function reload() {
    const seq = ++reloadSeq
    let finish = () => {}
    ready = new Promise<void>((resolve) => {
      finish = resolve
    })
    error.value = ''
    message.value = ''
    loading.value = true
    try {
      if (mode.value === 'import') {
        referCache.value = await gateway.loadDropdownRefers(
          editableFields.value,
          normalizeReferDict(table.value.refers),
          {},
        )
        if (seq !== reloadSeq) return
        count.value = 0
        if (!(await waitForHost())) return
        if (seq !== reloadSeq) return
        await grid.mountGrid(rowsToMatrix([], editableFields.value), [])
        dirty.resetSheetState([])
        await nextTick()
        syncRequiredComments(grid.getWorksheet(), editableFields.value)
        clearSelection()
        return
      }

      const req = request.value
      const res = await gateway.searchRecords(
        table.value.model,
        table.value.using || 'default',
        req?.page ?? 1,
        req?.size ?? 50,
        { query: req?.query },
      )
      if (seq !== reloadSeq) return
      referCache.value = await gateway.loadDropdownRefers(
        editableFields.value,
        normalizeReferDict(table.value.refers),
        normalizeReferDict(res.refers),
      )
      if (seq !== reloadSeq) return
      const list = (res.values || []).map((raw) =>
        fromSearchRow(raw, editableFields.value, referCache.value),
      )
      count.value = res.count ?? list.length
      const data = rowsToMatrix(list, editableFields.value)
      if (!(await waitForHost())) return
      if (seq !== reloadSeq) return
      await grid.mountGrid(data, list)
      dirty.resetSheetState(list)
      await nextTick()
      dirty.syncAllDirtyClasses()
      syncRequiredComments(grid.getWorksheet(), editableFields.value)
      clearSelection()
    } catch (e: unknown) {
      if (seq !== reloadSeq) return
      error.value = e instanceof Error ? e.message : String(e)
      count.value = 0
      if (await waitForHost()) {
        await grid.mountGrid(rowsToMatrix([], editableFields.value), [])
        dirty.resetSheetState([])
      }
    } finally {
      if (seq === reloadSeq) {
        loading.value = false
        finish()
      }
    }
  }

  function whenReady() {
    return ready
  }

  async function addRow() {
    await addRows(1)
  }

  async function addRows(n = 1) {
    if (mode.value === 'modify') {
      await appAlert('批量编辑不支持新增行')
      return
    }
    await ready
    const worksheet = grid.getWorksheet()
    if (!worksheet) return
    const before =
      typeof worksheet.getData === 'function'
        ? (worksheet.getData(false, true) as unknown[][])
        : []
    const placeholderOnly =
      dirty.originRows.value.length === 0 &&
      before.length === 1 &&
      (before[0] || []).every((cell) => String(cell ?? '').trim() === '')
    let countN = Math.floor(Number(n) || 1)
    if (countN < 1) countN = 1
    if (countN > 100) countN = 100
    let codes: string[] = []
    try {
      const docKind =
        table.value.model === 'fms.document'
          ? String(inputDefaults.value?.['basic.kind'] ?? '').trim()
          : ''
      const res = await gateway.allocSerials(table.value.model, countN, docKind || undefined)
      codes = res.codes || []
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      return
    }
    const newRows: SheetRow[] = []
    for (let i = 0; i < countN; i++) {
      newRows.push(newRowWithCode(codes[i] || '', editableFields.value, inputDefaults.value))
    }
    // origin 用空行（与粘贴扩行一致）：新行相对空快照会标 dirty，保存才能落库；
    // 仍先插 origin 再 insertRow，避免行索引错位
    dirty.insertOriginRows(
      0,
      Array.from({ length: countN }, () => ({})),
    )
    for (let i = countN - 1; i >= 0; i--) {
      const line = rowsToMatrix([newRows[i]], editableFields.value)[0]
      if (typeof worksheet.insertRow === 'function') {
        worksheet.insertRow(line, 0, 1)
      } else if (typeof worksheet.addRow === 'function') {
        worksheet.addRow(line)
      }
    }
    if (placeholderOnly && typeof worksheet.deleteRow === 'function') {
      worksheet.deleteRow(countN, 1)
    }
    await nextTick()
    dirty.syncAllDirtyClasses()
    syncRequiredComments(worksheet, editableFields.value, (r) => r < countN)
    grid.syncGridLayout()
  }

  /** 按表头（label / uukey / field）导入行，并分配序列号 */
  async function importMappedRows(headers: string[], dataRows: string[][]) {
    if (mode.value === 'modify') {
      await appAlert('批量编辑不支持导入')
      return
    }
    if (!dataRows.length) return
    const fields = editableFields.value
    const mapCol = (h: string) => {
      const key = h.trim().toLowerCase()
      return fields.find(
        (f) =>
          f.uukey.toLowerCase() === key ||
          f.field.toLowerCase() === key ||
          String(f.label || '')
            .toLowerCase()
            .replace(/\s+/g, '') === key.replace(/\s+/g, ''),
      )
    }
    const colFields = headers.map(mapCol)
    await addRows(Math.min(dataRows.length, 100))
    const all = readSheetRows()
    for (let i = 0; i < Math.min(dataRows.length, all.length); i++) {
      const row = all[i]
      if (!row) continue
      dataRows[i].forEach((cell, ci) => {
        const f = colFields[ci]
        if (!f || isSerial(f)) return
        row[fieldKey(f)] = String(cell ?? '').trim()
      })
    }
    const matrix = rowsToMatrix(all, fields)
    await grid.mountGrid(matrix, all)
    dirty.resetSheetState(Array.from({ length: all.length }, () => ({})))
    await nextTick()
    dirty.syncAllDirtyClasses()
    appToast(`已导入 ${Math.min(dataRows.length, all.length)} 行`)
  }

  function selectedRows(): SheetRow[] {
    const all = readSheetRows()
    const idxs = resolveSelectedIndices()
    if (!idxs.length) return []
    return idxs.map((i) => all[i]).filter(Boolean)
  }

  async function deleteSelected() {
    if (mode.value === 'modify') {
      await appAlert('批量编辑不支持删除，请返回列表操作')
      return
    }
    if (!getWorksheet()) return
    const idxs = resolveSelectedIndices()
    if (!idxs.length) {
      await appAlert('请先选中要移除的行')
      return
    }
    const ok = await appConfirm(`确定移除选中的 ${idxs.length} 行草稿？`, '移除确认', {
      confirmText: '移除',
    })
    if (!ok) return
    const worksheet = getWorksheet()
    if (!worksheet) return
    // 仅移除本地草稿行，不调删除接口
    const sorted = [...idxs].sort((a, b) => b - a)
    for (const i of sorted) {
      if (typeof worksheet.deleteRow === 'function') {
        worksheet.deleteRow(i)
      }
    }
    dirty.resetSheetState(readSheetRows())
    dirty.syncAllDirtyClasses()
    clearSelection()
    appToast(`已移除 ${idxs.length} 行`)
  }

  async function exportSelected() {
    const rows = selectedRows()
    if (!rows.length) {
      await appAlert('请先选中要导出的行')
      return
    }
    try {
      const ok = await exportRows({
        title: (table.value.title || table.value.model || '').trim() || table.value.model,
        fields: editableFields.value,
        rows: rows as unknown as Record<string, unknown>[],
      })
      if (ok) appToast(`已导出 ${rows.length} 条`)
    } catch (e: unknown) {
      await appAlert(e instanceof Error ? e.message : String(e))
    }
  }

  async function saveAll() {
    saving.value = true
    error.value = ''
    message.value = ''
    try {
      dirty.syncAllDirtyClasses()
      const all = readSheetRows()
      const dirtyIdxs = dirty.dirtyRowIndices()
      let rows = dirtyIdxs
        .map((i) => all[i])
        .filter((r): r is SheetRow => !!r && !isSheetRowEmpty(r))

      if (mode.value === 'modify') {
        const skipped = rows.filter((r) => !rowUUKey(r)).length
        rows = rows.filter((r) => !!rowUUKey(r))
        if (skipped) {
          await appAlert(`已忽略 ${skipped} 行无编号草稿（批量编辑仅保存已有记录）`)
        }
      } else {
        // 导入：一律按新建处理，去掉可能残留的编号
        rows = rows.map((r) => {
          const next = { ...r }
          delete next.uukey
          const ukField = editableFields.value.find((f) => isSerial(f))
          if (ukField) delete next[fieldKey(ukField)]
          return next
        })
      }

      if (!rows.length) {
        appToast(mode.value === 'import' ? '没有可导入的数据' : '没有需要保存的修改')
        return
      }

      const requiredMsg = validateRequiredRows(rows, editableFields.value)
      if (requiredMsg) {
        syncRequiredComments(getWorksheet(), editableFields.value, (r) => dirtyIdxs.includes(r))
        error.value = requiredMsg
        await appAlert(requiredMsg)
        return
      }

      // 无 uukey 且无修改的行已在 dirty 过滤中排除；此处只给「已改但无号」的新行补号。
      // fms.document 按行 kind 分前缀：交给后端 Upsert 分配，避免批量同号规则。
      const needSerialRows = rows.filter((r) => !rowUUKey(r))
      const codesByKind = new Map<string, string[]>()
      if (needSerialRows.length > 0 && table.value.model !== 'fms.document') {
        const res = await gateway.allocSerials(table.value.model, needSerialRows.length)
        codesByKind.set('', res.codes || [])
      } else if (needSerialRows.length > 0) {
        const groups = new Map<string, number>()
        for (const r of needSerialRows) {
          const k = String(r['basic.kind'] ?? r.kind ?? '').trim()
          groups.set(k, (groups.get(k) || 0) + 1)
        }
        for (const [k, n] of groups) {
          const res = await gateway.allocSerials(table.value.model, n, k || undefined)
          codesByKind.set(k, res.codes || [])
        }
      }
      const codeIdxByKind = new Map<string, number>()
      const batch = rows.map((r) => {
        const row = { ...r }
        if (!rowUUKey(row)) {
          const k =
            table.value.model === 'fms.document'
              ? String(row['basic.kind'] ?? row.kind ?? '').trim()
              : ''
          const pool = codesByKind.get(k) || codesByKind.get('') || []
          const idx = codeIdxByKind.get(k) || 0
          const code = pool[idx] || ''
          codeIdxByKind.set(k, idx + 1)
          if (code) {
            row.uukey = code
            const ukField = editableFields.value.find((f) => isSerial(f))
            if (ukField) row[fieldKey(ukField)] = code
          }
        }
        syncRowUUKey(row, editableFields.value)
        return rowToUpsertPayload(row, editableFields.value)
      })
      await gateway.upsertRecords(table.value.model, batch, table.value.using || 'default')
      const savedN = batch.length
      await reload()
      appToast(mode.value === 'import' ? `已导入 ${savedN} 行` : `已保存 ${savedN} 行`)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      appToast(error.value, 'error')
    } finally {
      saving.value = false
    }
  }

  onBeforeUnmount(() => {
    recalc.dispose()
    grid.destroyGrid()
  })

  watch(
    [
      () => table.value.model,
      () => table.value.using,
      () => mode.value,
      () => request.value?.page,
      () => request.value?.size,
      () => table.value.fields.map((f) => f.uukey).join(','),
      () => (table.value.sticky || []).join(','),
      () => JSON.stringify(table.value.refers || {}),
      () => JSON.stringify(request.value?.query || {}),
    ],
    async () => {
      // 在 loadInputDefaults 让出之前就挂上未完成的 ready，避免 whenReady 读到初始已完成的 Promise。
      let finishCycle = () => {}
      ready = new Promise<void>((resolve) => {
        finishCycle = resolve
      })
      try {
        await loadInputDefaults()
        await reload()
      } finally {
        finishCycle()
      }
    },
    { immediate: true },
  )

  return {
    host: grid.host,
    error,
    saving,
    message,
    loading,
    count,
    reload,
    whenReady,
    addRow,
    addRows,
    importMappedRows,
    saveAll,
    deleteSelected,
    exportSelected,
    collectRows: () => readSheetRows().filter((r) => !isSheetRowEmpty(r)),
  }
}

export function useSchemaSheetProps(props: SchemaSheetProps) {
  return useSchemaSheet(toRefs(props))
}
