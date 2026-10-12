<script setup lang="ts">
/**
 * ITEMS 明细表：走 FormSheet（jspreadsheet），对齐 duolali SheetForm 交互。
 * 保留原 GroupTable 的 props 契约，供 SchemaForm / RecordDialog 无感切换。
 */
import type { FormMode, ReferDict, SchemaField } from '@modoor/hooks'
import FormSheet from './FormSheet.vue'

defineProps<{
  title: string
  action: FormMode
  refers?: ReferDict
  fields: SchemaField[]
  values: Record<string, string>[]
  editable?: (field: SchemaField) => boolean
}>()
</script>

<template>
  <FormSheet
    class="group-table"
    :title="title"
    :action="action"
    :refers="refers"
    :fields="fields"
    :values="values"
    :editable="editable"
    table-width="100%"
  />
</template>
