<script setup lang="ts">
import type { SchemaRequest, SchemaTable } from '@modoor/hooks'
import { useSchemaSheetProps } from './useSchemaSheet'
import 'jsuites/dist/jsuites.css'
import 'jspreadsheet-ce/dist/jspreadsheet.css'

const props = defineProps<{
  table: SchemaTable
  request?: SchemaRequest
  mode?: 'modify' | 'import'
  autoHeight?: boolean
}>()

const {
  host,
  error,
  saving,
  message,
  loading,
  count,
  reload,
  addRow,
  addRows,
  whenReady,
  saveAll,
  collectRows,
  deleteSelected,
  exportSelected,
  importMappedRows,
} = useSchemaSheetProps(props)

defineExpose({
  reload,
  addRow,
  addRows,
  whenReady,
  saveAll,
  collectRows,
  deleteSelected,
  exportSelected,
  importMappedRows,
  get saving() {
    return saving.value
  },
  get count() {
    return count.value
  },
  get loading() {
    return loading.value
  },
  get error() {
    return error.value
  },
  get message() {
    return message.value
  },
})
</script>

<template>
  <div class="schema-sheet" :class="{ 'is-auto-height': autoHeight }">
    <div class="sheet-scroll">
      <div ref="host" class="jexcel-host" />
    </div>
  </div>
</template>

<style scoped>
.schema-sheet {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--panel, #fff);
}
.sheet-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 12px 12px;
}
.jexcel-host {
  height: 100%;
  width: 100%;
  min-height: 0;
}
.schema-sheet.is-auto-height {
  height: auto;
  min-height: 0;
}
.schema-sheet.is-auto-height .sheet-scroll {
  flex: 0 0 auto;
  overflow: visible;
}
.schema-sheet.is-auto-height .jexcel-host {
  height: auto;
}

.schema-sheet :deep(.jss_worksheet > thead > tr > td),
.schema-sheet :deep(.jexcel > thead > tr > td),
.schema-sheet :deep(.jss_worksheet > tbody > tr > td),
.schema-sheet :deep(.jexcel > tbody > tr > td) {
  font-size: 13px !important;
}
.schema-sheet :deep(.jss_worksheet > thead > tr > td),
.schema-sheet :deep(.jexcel > thead > tr > td) {
  background: #eef1f4;
  color: var(--muted, #6b6458);
  padding: 6px 0;
  font-weight: bold;
  font-size: 13px !important;
  text-align: center !important;
}
.schema-sheet :deep(td.sheet-cell-dirty),
.schema-sheet :deep(.jss_freezed.sheet-cell-dirty) {
  background-color: #ffd6d6 !important;
}
.schema-sheet :deep(.jss_worksheet td.jss_dropdown) {
  text-indent: -1rem !important;
  background-position-x: right 0 !important;
}
.schema-sheet :deep(.jss_worksheet td.jss_dropdown.editor) {
  text-indent: unset !important;
}
.schema-sheet :deep(.jss_worksheet td .jdropdown-header) {
  background-position-x: right 0 !important;
}
</style>
