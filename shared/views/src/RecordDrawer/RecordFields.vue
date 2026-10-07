<script setup lang="ts">
import { isLongTextField, isNumericField, type SchemaField } from '@modoor/hooks'
import './recordFields.css'

defineProps<{
  fields: SchemaField[]
  displayOf: (f: SchemaField) => string
}>()

/** `|` 只是表单换行，抽屉里按完整名称显示。 */
function fieldLabel(f: SchemaField) {
  return String(f.label || f.field || '').replaceAll('|', '')
}
</script>

<template>
  <div class="rd-fields">
    <div
      v-for="f in fields"
      :key="f.uukey"
      class="rd-field"
      :class="{ 'is-wide': isLongTextField(f) }"
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
