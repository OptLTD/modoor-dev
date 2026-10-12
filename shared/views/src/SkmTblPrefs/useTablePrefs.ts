/**
 * 列表字段 / 快捷筛选配置（View 层附加行为）。
 * 依赖 SchemaTable 暴露的 prefs host，草稿仅在此维护，应用后写回并持久化。
 */
import { computed, reactive, ref, type ComputedRef } from 'vue'
import type { TableColumnLayout } from '@modoor/hooks'

export type PrefsPanelItem = {
  id: string
  label: string
  visible: boolean
}

export type TableLayoutHost = {
  model: ComputedRef<string> | { value: string }
  using: ComputedRef<string> | { value: string }
  snapshot: () => TableColumnLayout | null
  apply: (layout: TableColumnLayout | null) => void
  save: () => void
  buildColumnItems: (order: string[] | null, hidden: string[] | null) => PrefsPanelItem[]
  buildFilterItems: (order: string[] | null, hidden: string[] | null) => PrefsPanelItem[]
}

function sameKeyList(a: string[] | null, b: string[] | null) {
  if (a === b) return true
  if (a == null || b == null) return a == null && b == null
  if (a.length !== b.length) return false
  return a.every((k, i) => k === b[i])
}

function cloneKeys(keys: string[] | null | undefined): string[] | null {
  return keys?.length ? [...keys] : keys === null || keys === undefined ? null : []
}

export function useTablePrefs(getHost: () => TableLayoutHost | null | undefined) {
  const open = ref(false)
  const tab = ref<'columns' | 'filters'>('columns')
  const draftColumnOrder = ref<string[] | null>(null)
  const draftColumnHidden = ref<string[] | null>(null)
  const draftFilterOrder = ref<string[] | null>(null)
  const draftFilterHidden = ref<string[] | null>(null)

  function host() {
    return getHost() || null
  }

  function beginEdit() {
    const h = host()
    const snap = h?.snapshot() || null
    if (!snap) {
      draftColumnOrder.value = null
      draftColumnHidden.value = null
      draftFilterOrder.value = null
      draftFilterHidden.value = null
      return
    }
    const colsOn = snap.order.length > 0 || snap.hidden.length > 0
    draftColumnOrder.value = colsOn ? cloneKeys(snap.order) : null
    draftColumnHidden.value = colsOn ? cloneKeys(snap.hidden) : null
    const filtersOn = (snap.filterOrder?.length || 0) > 0 || (snap.filterHidden?.length || 0) > 0
    draftFilterOrder.value = filtersOn ? cloneKeys(snap.filterOrder || []) : null
    draftFilterHidden.value = filtersOn ? cloneKeys(snap.filterHidden || []) : null
  }

  const columnItems = computed(() => {
    const h = host()
    if (!h) return [] as PrefsPanelItem[]
    return h.buildColumnItems(draftColumnOrder.value, draftColumnHidden.value)
  })

  const filterItems = computed(() => {
    const h = host()
    if (!h) return [] as PrefsPanelItem[]
    return h.buildFilterItems(draftFilterOrder.value, draftFilterHidden.value)
  })

  const columnsCustomized = computed(
    () => draftColumnOrder.value !== null || draftColumnHidden.value !== null,
  )
  const filtersCustomized = computed(
    () => draftFilterOrder.value !== null || draftFilterHidden.value !== null,
  )

  const columnsDirty = computed(() => {
    const snap = host()?.snapshot()
    const appliedOrder = snap && (snap.order.length || snap.hidden.length) ? snap.order : null
    const appliedHidden = snap && (snap.order.length || snap.hidden.length) ? snap.hidden : null
    return (
      !sameKeyList(draftColumnOrder.value, appliedOrder) ||
      !sameKeyList(draftColumnHidden.value, appliedHidden)
    )
  })

  const filtersDirty = computed(() => {
    const snap = host()?.snapshot()
    const on = !!snap && ((snap.filterOrder?.length || 0) > 0 || (snap.filterHidden?.length || 0) > 0)
    const appliedOrder = on ? snap!.filterOrder || [] : null
    const appliedHidden = on ? snap!.filterHidden || [] : null
    return (
      !sameKeyList(draftFilterOrder.value, appliedOrder) ||
      !sameKeyList(draftFilterHidden.value, appliedHidden)
    )
  })

  function toggleColumn(id: string) {
    const key = String(id || '').trim()
    if (!key) return
    const items = columnItems.value
    const hidden = new Set(
      draftColumnHidden.value ?? items.filter((item) => !item.visible).map((item) => item.id),
    )
    if (hidden.has(key)) hidden.delete(key)
    else if (items.filter((item) => item.visible).length <= 1) return
    else hidden.add(key)
    if (!draftColumnOrder.value?.length) draftColumnOrder.value = items.map((item) => item.id)
    draftColumnHidden.value = [...hidden]
  }

  function moveColumn(from: number, to: number) {
    const items = columnItems.value
    if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return
    const order = items.map((item) => item.id)
    const [row] = order.splice(from, 1)
    order.splice(to, 0, row)
    if (!draftColumnHidden.value) {
      draftColumnHidden.value = items.filter((item) => !item.visible).map((item) => item.id)
    }
    draftColumnOrder.value = order
  }

  function resetColumns() {
    draftColumnOrder.value = null
    draftColumnHidden.value = null
  }

  function applyAll() {
    const h = host()
    if (!h) return
    const colsOn = draftColumnOrder.value !== null || draftColumnHidden.value !== null
    const filtersOn = draftFilterOrder.value !== null || draftFilterHidden.value !== null
    if (!colsOn && !filtersOn) {
      h.apply(null)
    } else {
      h.apply({
        order: colsOn ? draftColumnOrder.value || [] : [],
        hidden: colsOn ? draftColumnHidden.value || [] : [],
        ...(filtersOn
          ? {
              filterOrder: draftFilterOrder.value || [],
              filterHidden: draftFilterHidden.value || [],
            }
          : {}),
      })
    }
    h.save()
    beginEdit()
  }

  function applyColumns() {
    applyAll()
  }

  function toggleFilter(id: string) {
    const key = String(id || '').trim()
    if (!key) return
    const items = filterItems.value
    const hidden = new Set(
      draftFilterHidden.value ?? items.filter((item) => !item.visible).map((item) => item.id),
    )
    if (hidden.has(key)) hidden.delete(key)
    else hidden.add(key)
    if (!draftFilterOrder.value?.length) draftFilterOrder.value = items.map((item) => item.id)
    draftFilterHidden.value = [...hidden]
  }

  function moveFilter(from: number, to: number) {
    const items = filterItems.value
    if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return
    const order = items.map((item) => item.id)
    const [row] = order.splice(from, 1)
    order.splice(to, 0, row)
    if (!draftFilterHidden.value) {
      draftFilterHidden.value = items.filter((item) => !item.visible).map((item) => item.id)
    }
    draftFilterOrder.value = order
  }

  function resetFilters() {
    draftFilterOrder.value = null
    draftFilterHidden.value = null
  }

  function applyFilters() {
    applyAll()
  }

  function close() {
    open.value = false
  }

  function toggleOpen(onCloseFilter?: () => void) {
    open.value = !open.value
    if (open.value) {
      onCloseFilter?.()
      beginEdit()
    }
  }

  return reactive({
    open,
    tab,
    columnItems,
    filterItems,
    columnsCustomized,
    filtersCustomized,
    columnsDirty,
    filtersDirty,
    toggleOpen,
    close,
    toggleColumn,
    moveColumn,
    resetColumns,
    applyColumns,
    toggleFilter,
    moveFilter,
    resetFilters,
    applyFilters,
    beginEdit,
  })
}

export type TablePrefsApi = ReturnType<typeof useTablePrefs>
