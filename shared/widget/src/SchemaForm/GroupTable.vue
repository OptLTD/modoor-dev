<script setup lang="ts">
import { computed } from 'vue'
import type { FormMode, SchemaField, ReferDict } from '@modoor/hooks'
import { isOnlyDate, isOnlyMonth, isRequired, t } from '@modoor/hooks'
import SelectBox from '../SelectBox'
import {
  fieldSelectOptions,
  isDateField,
  isNumericFormField,
  isOptionalField,
  isRelationField,
} from './fieldKinds'

const props = defineProps<{
  title: string
  action: FormMode
  refers?: ReferDict
  fields: SchemaField[]
  values: Record<string, string>[]
  editable?: (field: SchemaField) => boolean
}>()

function fieldEditable(f: SchemaField) {
  return props.editable ? props.editable(f) : true
}

const canMutate = computed(() => props.fields.some((f) => fieldEditable(f)))

function optionsOf(f: SchemaField, row: Record<string, string>) {
  const parentField = String(f.extra?.parentField || '').trim()
  const parentValue = parentField ? String(row[parentField] ?? '') : ''
  return fieldSelectOptions(f, props.refers, parentValue)
}

function labelOf(f: SchemaField) {
  return String(f.label || f.field || '')
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean)
    .join('')
}

function addRow() {
  const row: Record<string, string> = {}
  for (const f of props.fields) row[f.field] = ''
  props.values.push(row)
}

function removeRow(index: number) {
  props.values.splice(index, 1)
}
</script>

<template>
  <section class="group-table">
    <header class="group-head">
      <strong>{{ title }}</strong>
      <button v-if="canMutate" type="button" class="link" @click="addRow">{{ t('widget.addRow') }}</button>
    </header>
    <div class="group-scroll">
      <table>
        <thead>
          <tr>
            <th v-for="f in fields" :key="f.uukey">
              {{ labelOf(f) }}<span v-if="isRequired(f)" class="req">*</span>
            </th>
            <th v-if="canMutate" class="row-op"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!values.length">
            <td class="empty" :colspan="fields.length + (canMutate ? 1 : 0)">{{ t('widget.groupEmpty') }}</td>
          </tr>
          <tr v-for="(row, index) in values" :key="index">
            <td v-for="f in fields" :key="f.uukey">
              <SelectBox
                v-if="isRelationField(f) || isOptionalField(f)"
                v-model="row[f.field]"
                :options="optionsOf(f, row)"
                :disabled="!fieldEditable(f)"
                bare
              />
              <input
                v-else-if="isDateField(f)"
                v-model="row[f.field]"
                :type="isOnlyMonth(f) ? 'month' : isOnlyDate(f) ? 'date' : 'datetime-local'"
                :disabled="!fieldEditable(f)"
              />
              <input
                v-else-if="isNumericFormField(f)"
                v-model="row[f.field]"
                type="number"
                :disabled="!fieldEditable(f)"
              />
              <input v-else v-model="row[f.field]" type="text" :disabled="!fieldEditable(f)" />
            </td>
            <td v-if="canMutate" class="row-op">
              <button type="button" class="link" @click="removeRow(index)">
                {{ t('widget.delete') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.group-table {
  margin-top: 16px;
  min-width: 0;
}
.group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.group-head strong {
  font-size: 0.9rem;
  font-weight: 600;
}
.link {
  border: 0;
  background: none;
  color: var(--accent, #0f6a5a);
  cursor: pointer;
  font: inherit;
  font-size: 0.82rem;
  padding: 0;
}
.group-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
th {
  text-align: left;
  font-weight: 500;
  color: var(--muted, #6b6458);
  padding: 4px 8px;
  border-bottom: 1px solid var(--line, #e4e0d8);
  white-space: nowrap;
}
td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--line, #e4e0d8);
  vertical-align: middle;
  min-width: 7rem;
}
.row-op {
  width: 3rem;
  min-width: 3rem;
  text-align: right;
}
.empty {
  color: var(--muted, #6b6458);
  text-align: center;
  padding: 10px 8px;
}
.req {
  color: var(--danger, #a33b2b);
  margin-left: 2px;
}
td :deep(.select-box),
td input {
  width: 100%;
  min-width: 0;
}
td input {
  min-height: 30px;
  border: 0;
  border-bottom: 1px solid #c5cad3;
  border-radius: 0;
  padding: 4px 6px;
  font: inherit;
  font-size: 0.82rem;
  color: var(--ink, #1c1914);
  background: #fff;
  outline: none;
}
td input:focus {
  border-bottom-color: var(--accent, #0f6a5a);
}
td :deep(.select-box.bare .select-trigger) {
  min-height: 30px;
  border: 0;
  border-bottom: 1px solid #c5cad3;
  border-radius: 0;
  padding: 4px 6px;
  background: #fff;
  box-shadow: none;
}
</style>
