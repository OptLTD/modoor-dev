<script setup lang="ts">
/**
 * SkmTbl（SchemaTable）+ 列设置 + 条件筛选（View 层页面组合）。
 * 下钻等纯展示场景请直接用 @modoor/widget/SchemaTable。
 */
import { computed, ref, useAttrs, watch } from 'vue'
import { useI18n } from '@modoor/hooks'
import type { SchemaClick, SchemaField, SchemaTable } from '@modoor/hooks'
import type { FilterDraft } from '@modoor/hooks'
import SchemaTableView from '@modoor/widget/SchemaTable'
import SvgIcon from '@modoor/widget/SvgIcon'
import TablePrefs from './TablePrefs.vue'
import TableFilterDrawer from './TableFilterDrawer.vue'
import { useTablePrefs, type TableLayoutHost } from './useTablePrefs'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    table: SchemaTable
    using?: string
    actionMin?: number
    hideBody?: boolean
    hideFilter?: boolean
    hidePagination?: boolean
  }>(),
  {
    hideBody: false,
    hidePagination: false,
    hideFilter: false,
  },
)

const emit = defineEmits<{
  'button-click': [
    payload: { click: SchemaClick; keys: string[]; records: Record<string, unknown>[] },
  ]
  'action-click': [payload: { click: SchemaClick; record: Record<string, unknown>; key: string }]
  'record-click': [
    payload: {
      model: string
      uukey?: string
      title?: string
      field?: SchemaField
      record?: Record<string, unknown>
      lookup?: Record<string, unknown>
    },
  ]
  'request-change': [
    payload: { page: number; size: number; query?: Record<string, unknown> },
  ]
  refresh: []
}>()

const attrs = useAttrs()
const { t } = useI18n()

type TableFilterApi = {
  panelFilterOpen: boolean
  activeFilterCount: number
  panelFilterFields: SchemaField[]
  appliedFilters: Record<string, FilterDraft>
  togglePanelFilter: () => void
  closePanelFilter: () => void
  clearAllFilters: () => void
  onPanelFilters: (next: Record<string, FilterDraft>) => void
}

type TableExpose = {
  api: {
    prefs: TableLayoutHost
    filter: TableFilterApi
    list: { theRefers: Record<string, unknown>; loading: boolean }
  }
  reload: () => void
  getListRequest: () => unknown
  getSelectedRows: () => Record<string, unknown>[]
  getVisibleRows: () => Record<string, unknown>[]
  getSelectedKeys: () => string[]
  exportByQuery: (...args: unknown[]) => unknown
  exportSelected: () => unknown
  deleteSelected: () => unknown
}

const tableRef = ref<TableExpose | null>(null)

const prefs = useTablePrefs(() => tableRef.value?.api.prefs)

const showPrefsBtn = computed(() => !props.hideBody)
const showFilterBtn = computed(() => !props.hideFilter)
const filterOpen = computed(() => !!tableRef.value?.api.filter.panelFilterOpen)
const filterCount = computed(() => tableRef.value?.api.filter.activeFilterCount || 0)
const filterFields = computed(() => tableRef.value?.api.filter.panelFilterFields || [])
const filterValue = computed(() => tableRef.value?.api.filter.appliedFilters || {})
const filterRefers = computed(() => tableRef.value?.api.list.theRefers)

function onTogglePrefs() {
  prefs.toggleOpen(() => tableRef.value?.api.filter.closePanelFilter())
}

function onToggleFilter() {
  if (!filterOpen.value) prefs.close()
  tableRef.value?.api.filter.togglePanelFilter()
}

watch(
  () => tableRef.value?.api.filter.panelFilterOpen,
  (open) => {
    if (open) prefs.close()
  },
)

defineExpose({
  reload: () => tableRef.value?.reload(),
  getListRequest: () => tableRef.value?.getListRequest(),
  getSelectedRows: () => tableRef.value?.getSelectedRows() || [],
  getVisibleRows: () => tableRef.value?.getVisibleRows() || [],
  getSelectedKeys: () => tableRef.value?.getSelectedKeys() || [],
  exportByQuery: (...args: unknown[]) => tableRef.value?.exportByQuery(...args),
  exportSelected: () => tableRef.value?.exportSelected(),
  deleteSelected: () => tableRef.value?.deleteSelected(),
})
</script>

<template>
  <SchemaTableView
    ref="tableRef"
    v-bind="{ ...attrs, ...props }"
    @button-click="emit('button-click', $event)"
    @action-click="emit('action-click', $event)"
    @record-click="emit('record-click', $event)"
    @request-change="emit('request-change', $event)"
    @refresh="emit('refresh')"
  >
    <template v-if="showPrefsBtn || showFilterBtn" #toolbar-right>
      <button
        v-if="showPrefsBtn"
        type="button"
        class="icon-btn"
        :class="{ active: prefs.open }"
        :title="t('widget.columns')"
        :aria-pressed="prefs.open"
        @click="onTogglePrefs"
      >
        <SvgIcon name="columns" />
      </button>
      <button
        v-if="showFilterBtn"
        type="button"
        class="icon-btn"
        :class="{ active: filterOpen }"
        :title="t('widget.filter')"
        @click="onToggleFilter"
      >
        <SvgIcon name="filter" />
        <span v-if="filterCount" class="icon-badge">{{ filterCount }}</span>
      </button>
    </template>
    <template v-if="$slots['toolbar-extra']" #toolbar-extra>
      <slot name="toolbar-extra" />
    </template>
  </SchemaTableView>

  <TablePrefs :prefs="prefs" :hide-filter="hideFilter" />
  <TableFilterDrawer
    v-if="showFilterBtn"
    :open="filterOpen"
    :fields="filterFields"
    :model-value="filterValue"
    :refers="filterRefers"
    @close="tableRef?.api.filter.closePanelFilter()"
    @reset="tableRef?.api.filter.clearAllFilters()"
    @update="tableRef?.api.filter.onPanelFilters($event)"
  />
</template>
