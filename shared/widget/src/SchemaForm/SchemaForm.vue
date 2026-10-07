<script setup lang="ts">
import type { FormMode, SchemaField, ReferDict } from '@modoor/hooks'
import { fieldKey, isMultiple, isOnlyDate, isOnlyMonth, isRequired, t } from '@modoor/hooks'
import SelectBox from '../SelectBox'
import FileField from './FileField.vue'
import GroupTable from './GroupTable.vue'
import {
  fieldSelectOptions,
  isDateField,
  isFullRowField,
  isNumericFormField,
  isOptionalField,
  isRelationField,
  isSerialField,
  isTextareaField,
  isUploadField,
  uploadAccept,
} from './fieldKinds'

export type RepeatGroup = {
  uukey: string
  title: string
  fields: SchemaField[]
}

const props = withDefaults(
  defineProps<{
    fields: SchemaField[]
    form: Record<string, string | string[]>
    mode: FormMode
    refers?: ReferDict
    canEdit?: (field: SchemaField) => boolean
    /** Controls per row. Dialogs stay at 2; a full-width card can use 6. */
    columns?: number
    /** GROUPED + extra.multiple：少字段，表格一行一条 */
    repeatGroups?: RepeatGroup[]
    groupRows?: Record<string, Record<string, string>[]>
  }>(),
  { columns: 2, repeatGroups: () => [], groupRows: () => ({}) },
)

function editable(f: SchemaField) {
  return props.canEdit ? props.canEdit(f) : true
}

function isSubjectField(f: SchemaField) {
  const name = String(f.field || '').trim()
  const key = fieldKey(f)
  return name === 'subject' || key === 'subject' || key.endsWith('.subject')
}

function fieldText(f: SchemaField) {
  const raw = props.form[fieldKey(f)]
  if (Array.isArray(raw)) return raw.map((item) => String(item || '').trim()).filter(Boolean).join(' ')
  return String(raw || '').trim()
}

/** 上传当下的字段名和 subject。之后改了名称或 subject，不再回写这些标签。 */
function uploadTags(f: SchemaField) {
  const tags: string[] = []
  const label = labelLines(f).join('')
  if (label) tags.push(label)
  const subjectField = props.fields.find(isSubjectField)
  const subject = subjectField ? fieldText(subjectField) : ''
  if (subject && !tags.includes(subject)) tags.push(subject)
  return tags
}

function optionsOf(f: SchemaField) {
  const parentField = String(f.extra?.parentField || '').trim()
  const parentValue = parentField ? String(props.form[parentField] ?? '') : ''
  return fieldSelectOptions(f, props.refers, parentValue)
}

/** label 中 `|` 表示换行（如 行驶时长|(小时)） */
function labelLines(f: SchemaField): string[] {
  const raw = String(f.label || f.field || '')
  return raw
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean)
}
</script>

<template>
  <div
    class="schema-fields"
    :class="{ wide: columns > 2 }"
    :style="{ '--cols': String(columns) }"
  >
    <div
      v-for="f in fields"
      :key="f.uukey"
      class="field"
      :class="{ full: isFullRowField(f) || isTextareaField(f), upload: isUploadField(f) }"
    >
      <span class="field-label" :class="{ 'is-required': isRequired(f), wrapped: labelLines(f).length > 1 }">
        <span class="field-label-text">
          <span v-for="(line, li) in labelLines(f)" :key="li" class="field-label-line">{{
            line
          }}</span>
        </span>
        <span v-if="isRequired(f)" class="req">*</span>
      </span>
      <span class="field-control">
        <SelectBox
          v-if="isRelationField(f) || isOptionalField(f)"
          v-model="form[fieldKey(f)]"
          :options="optionsOf(f)"
          :multiple="isMultiple(f)"
          :disabled="!editable(f)"
          bare
        />
        <input
          v-else-if="isDateField(f)"
          v-model="form[fieldKey(f)] as string"
          :type="isOnlyMonth(f) ? 'month' : isOnlyDate(f) ? 'date' : 'datetime-local'"
          :disabled="!editable(f)"
        />
        <input
          v-else-if="isNumericFormField(f)"
          v-model="form[fieldKey(f)] as string"
          type="number"
          class="num"
          :disabled="!editable(f)"
        />
        <textarea
          v-else-if="isTextareaField(f)"
          v-model="form[fieldKey(f)] as string"
          rows="3"
          :disabled="!editable(f)"
        />
        <FileField
          v-else-if="isUploadField(f)"
          v-model="form[fieldKey(f)]"
          :multiple="isMultiple(f)"
          :accept="uploadAccept(f)"
          :disabled="!editable(f)"
          :tags="uploadTags(f)"
        />
        <input
          v-else
          v-model="form[fieldKey(f)] as string"
          type="text"
          :disabled="!editable(f)"
          :placeholder="mode === 'create' && isSerialField(f) ? t('widget.serialAuto') : ''"
        />
      </span>
    </div>
    <div v-if="repeatGroups.length" class="group-block">
      <GroupTable
        v-for="g in repeatGroups"
        :key="g.uukey"
        :title="g.title"
        :fields="g.fields"
        :values="groupRows[g.uukey] || []"
        :action="mode"
        :refers="refers"
        :editable="canEdit"
      />
    </div>
  </div>
</template>

<style scoped>
.schema-fields {
  display: grid;
  grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr));
  gap: 14px 20px;
}
.group-block {
  grid-column: 1 / -1;
}
.schema-fields.wide {
  gap: 8px 6px;
}
.schema-fields.wide .field-label {
  width: 4rem;
}
.field {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
  min-width: 0;
  border: 0;
  background: transparent;
}
.field.full {
  grid-column: 1 / -1;
  align-items: flex-start;
}
.field-label {
  flex: 0 0 auto;
  width: 5.5rem;
  max-width: 36%;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  padding: 0;
  font-size: 0.85rem;
  /* font-weight: 500; */
  color: var(--ink, #1c1914);
  background: transparent;
  border: 0;
  line-height: 1.25;
  text-align: right;
  box-sizing: border-box;
}
.field-label.is-required {
  color: var(--danger, #a33b2b);
}
.field-label.wrapped {
  font-size: 0.75rem;
}
.field-label-text {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  min-width: 0;
}
.field-label-line {
  display: block;
  word-break: break-word;
}
.req {
  color: inherit;
}
.field-control {
  flex: 1 1 auto;
  display: flex;
  align-items: stretch;
  min-width: 0;
}
.field-control :deep(.select-box),
.field-control input {
  flex: 1;
  width: 100%;
  min-width: 0;
}
.field-control input {
  min-height: 32px;
  border: 0;
  border-bottom: 1px solid #c5cad3;
  border-radius: 0;
  padding: 5px 8px;
  font: inherit;
  font-size: 0.88rem;
  color: var(--ink, #1c1914);
  background: #fff;
  outline: none;
  transition:
    border-color 0.12s ease,
    background 0.12s ease;
}
.field-control input:focus {
  border-bottom-color: var(--accent, #0f6a5a);
  background: #fff;
}
.field-control input:disabled,
.field-control input:read-only {
  color: var(--muted, #6b6458);
  background: #eef1f4;
  border-bottom-color: #d5dae2;
  cursor: not-allowed;
  opacity: 1;
}
.field-control :deep(.select-box.bare .select-trigger) {
  min-height: 32px;
  border: 0;
  border-bottom: 1px solid #c5cad3;
  border-radius: 0;
  padding: 5px 8px;
  background: #fff;
  box-shadow: none;
  cursor: pointer;
}
.field-control :deep(.select-box.bare .select-trigger:hover:not(.disabled)),
.field-control :deep(.select-box.bare .select-trigger:focus-visible) {
  border-bottom-color: var(--accent, #0f6a5a);
  background: #fff;
}
.field-control :deep(.select-box.bare.disabled .select-trigger),
.field-control :deep(.select-box.bare .select-trigger.disabled) {
  background: #eef1f4;
  border-bottom-color: #d5dae2;
  color: var(--muted, #6b6458);
  cursor: not-allowed;
}
.field-control textarea {
  flex: 1;
  width: 100%;
  min-width: 0;
  min-height: 4.5rem;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 0;
  padding: 8px 10px;
  font: inherit;
  line-height: 1.4;
  resize: vertical;
  background: #fff;
  outline: none;
}
.field-control textarea:focus {
  border-color: color-mix(in srgb, var(--accent, #0f6a5a) 55%, var(--line));
}
.field-control textarea:disabled,
.field-control textarea:read-only {
  background: #eef1f4;
  color: var(--muted);
  cursor: not-allowed;
}
.field .num {
  font-variant-numeric: tabular-nums;
}
@media (max-width: 1100px) {
  .schema-fields {
    grid-template-columns: repeat(min(var(--cols, 2), 3), minmax(0, 1fr));
  }
}
@media (max-width: 960px) {
  .schema-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .schema-fields {
    grid-template-columns: 1fr;
  }
  .field-label {
    justify-content: flex-start;
    text-align: left;
  }
  .field-label-text {
    align-items: flex-start;
  }
}
</style>
