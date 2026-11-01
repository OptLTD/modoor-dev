<script setup lang="ts">
/**
 * Header-filter choice list rendered inline inside `.filter-pop`.
 *
 * A nested SelectBox popup would float over the filter's own “应用” button;
 * keeping the options in flow makes the popover taller instead of covering it.
 */
import { computed, ref } from 'vue'
import { useI18n } from '@modoor/hooks'
import type { SelectOption } from '../SelectBox/SelectBox.vue'

const props = withDefaults(
  defineProps<{
    modelValue: string[]
    options: SelectOption[]
    searchable?: boolean
    maxHeight?: number
  }>(),
  { searchable: true, maxHeight: 200 },
)

const emit = defineEmits<{ 'update:modelValue': [string[]] }>()
const { t } = useI18n()
const search = ref('')

const selected = computed(() => new Set(props.modelValue))
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter(
    (o) =>
      o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
  )
})

function toggle(value: string) {
  const next = new Set(props.modelValue)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  emit('update:modelValue', Array.from(next))
}
</script>

<template>
  <div class="filter-choice">
    <input
      v-if="searchable && options.length > 6"
      v-model="search"
      type="search"
      class="filter-choice-search"
      :placeholder="t('widget.filterValue')"
    />
    <div class="filter-choice-list" :style="{ maxHeight: `${maxHeight}px` }">
      <label
        v-for="opt in filtered"
        :key="opt.value"
        class="filter-choice-option"
      >
        <input
          type="checkbox"
          :checked="selected.has(opt.value)"
          @change="toggle(opt.value)"
        />
        <span class="filter-choice-label">{{ opt.label }}</span>
      </label>
      <p v-if="!filtered.length" class="filter-choice-empty">
        {{ t('widget.empty') }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.filter-choice {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 6px;
}
.filter-choice-search {
  width: 100%;
  height: 30px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 0 8px;
  font: inherit;
  font-size: 12px;
  color: var(--ink);
  background: #fff;
  box-sizing: border-box;
  outline: none;
}
.filter-choice-search:focus {
  border-color: var(--accent);
}
.filter-choice-list {
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  padding: 4px;
}
.filter-choice-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.4;
  color: var(--ink);
  cursor: pointer;
}
.filter-choice-option:hover {
  background: color-mix(in srgb, var(--accent) 8%, #fff);
}
.filter-choice-option input {
  flex-shrink: 0;
  margin: 0;
  accent-color: var(--accent);
}
.filter-choice-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.filter-choice-empty {
  margin: 0;
  padding: 12px 6px;
  text-align: center;
  font-size: 12px;
  color: var(--muted);
}
</style>
