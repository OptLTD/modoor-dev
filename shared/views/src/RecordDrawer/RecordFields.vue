<script setup lang="ts">
import { isLongTextField, isNumericField, type SchemaField } from '@modoor/hooks'
import './recordFields.css'

const props = defineProps<{
  fields: SchemaField[]
  displayOf: (f: SchemaField) => string
  /**
   * 指定哪些字段独占整行；不传时沿用默认规则
   * （长文本 + LOCATION 整行），传空数组则全部按网格排列。
   */
  wideFields?: string[]
}>()

/** `|` 只是表单换行，抽屉里按完整名称显示。 */
function fieldLabel(f: SchemaField) {
  return String(f.label || f.field || '').replaceAll('|', '')
}

function isWide(f: SchemaField) {
  if (props.wideFields) {
    return props.wideFields.includes(f.uukey || f.index || '')
  }
  return isLongTextField(f) || String(f.ftype).toUpperCase() === 'LOCATION'
}
</script>

<template>
  <div class="rd-fields">
    <div
      v-for="f in fields"
      :key="f.uukey"
      class="rd-field"
      :class="{ 'is-wide': isWide(f) }"
    >
      <div class="rd-field-label">{{ fieldLabel(f) }}</div>
      <div
        class="rd-field-value"
        :class="{
          num: isNumericField(f),
          'is-empty': !String(displayOf(f) ?? '').trim(),
        }"
      >
        {{ displayOf(f) || '—' }}
      </div>
    </div>
  </div>
</template>
