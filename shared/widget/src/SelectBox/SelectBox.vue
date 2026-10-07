<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from '@modoor/hooks'
import SvgIcon from '../SvgIcon/SvgIcon.vue'

export type SelectOption = {
  label: string
  value: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: string | string[]
    options: SelectOption[]
    multiple?: boolean
    disabled?: boolean
    placeholder?: string
    clearable?: boolean
    /** 面板内搜索过滤选项 */
    searchable?: boolean
    /** 嵌入外框时去掉自身边框 */
    bare?: boolean
  }>(),
  {
    modelValue: '',
    multiple: false,
    disabled: false,
    placeholder: '请选择',
    clearable: true,
    searchable: false,
    bare: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [string | string[]]
}>()

const { t } = useI18n()
const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const searchEl = ref<HTMLInputElement | null>(null)
const panelStyle = ref<Record<string, string>>({})
const search = ref('')

const selected = computed<string[]>(() => {
  const v = props.modelValue
  if (props.multiple) {
    if (Array.isArray(v)) return v.map(String).filter(Boolean)
    if (typeof v === 'string' && v.trim()) {
      return v.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)
    }
    return []
  }
  if (Array.isArray(v)) return v[0] ? [String(v[0])] : []
  return v ? [String(v)] : []
})

const filteredOptions = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return props.options
  return props.options.filter(
    (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q),
  )
})

const displayText = computed(() => {
  if (!selected.value.length) return ''
  if (props.multiple) {
    return selected.value
      .map((val) => props.options.find((o) => o.value === val)?.label || val)
      .join('、')
  }
  const hit = props.options.find((o) => o.value === selected.value[0])
  return hit?.label || selected.value[0] || ''
})

function emitValue(vals: string[]) {
  if (props.multiple) emit('update:modelValue', vals)
  else emit('update:modelValue', vals[0] || '')
}

function isSelected(val: string) {
  return selected.value.includes(val)
}

function pick(opt: SelectOption) {
  if (props.disabled) return
  if (props.multiple) {
    const next = isSelected(opt.value)
      ? selected.value.filter((v) => v !== opt.value)
      : [...selected.value, opt.value]
    emitValue(next)
  } else {
    emitValue([opt.value])
    open.value = false
  }
}

function clear(e?: Event) {
  e?.stopPropagation()
  if (props.disabled) return
  emitValue([])
}

function updatePanelPos() {
  const el = triggerEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const maxH = 260
  const spaceBelow = window.innerHeight - r.bottom - 8
  const placeUp = spaceBelow < 140 && r.top > spaceBelow
  panelStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, r.left)}px`,
    width: `${Math.max(r.width, 160)}px`,
    zIndex: 'var(--z-pop, 10120)',
    ...(placeUp
      ? {
          bottom: `${window.innerHeight - r.top + 4}px`,
          top: 'auto',
          maxHeight: `${Math.min(maxH, r.top - 8)}px`,
        }
      : {
          top: `${r.bottom + 4}px`,
          bottom: 'auto',
          maxHeight: `${Math.min(maxH, spaceBelow)}px`,
        }),
  }
}

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    search.value = ''
    await nextTick()
    updatePanelPos()
    if (props.searchable) searchEl.value?.focus()
  }
}

function onDocPointer(e: Event) {
  const t = e.target as Node
  if (rootEl.value?.contains(t)) return
  if (panelEl.value?.contains(t)) return
  open.value = false
}

function onScrollOrResize() {
  if (open.value) updatePanelPos()
}

watch(open, (v) => {
  if (v) {
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
  } else {
    window.removeEventListener('scroll', onScrollOrResize, true)
    window.removeEventListener('resize', onScrollOrResize)
  }
})

onMounted(() => {
  document.addEventListener('mousedown', onDocPointer)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocPointer)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<template>
  <div ref="rootEl" class="select-box" :class="{ disabled, bare }">
    <div
      ref="triggerEl"
      class="select-trigger"
      :class="{ disabled }"
      role="button"
      tabindex="0"
      @click="toggle"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
    >
      <span v-if="multiple && selected.length" class="tags">
        <span v-for="val in selected" :key="val" class="tag">
          <span class="tag-label">{{ options.find((o) => o.value === val)?.label || val }}</span>
          <span
            class="tag-x"
            role="button"
            tabindex="-1"
            @click.stop="pick({ label: '', value: val })"
            @keydown.enter.prevent.stop="pick({ label: '', value: val })"
            @keydown.space.prevent.stop="pick({ label: '', value: val })"
          >
            ×
          </span>
        </span>
      </span>
      <span v-else-if="displayText" class="value truncate">{{ displayText }}</span>
      <span v-else class="placeholder truncate">{{ placeholder }}</span>
      <span class="trailing">
        <span
          v-if="clearable && selected.length && !disabled"
          class="clear-btn"
          role="button"
          tabindex="-1"
          :title="t('widget.clear')"
          @click.stop="clear"
          @keydown.enter.prevent.stop="clear"
          @keydown.space.prevent.stop="clear"
        >
          ×
        </span>
        <SvgIcon name="chevron-down" class="chevron" :class="{ open }" :size="12" />
      </span>
    </div>

    <Teleport to="body">
      <div v-if="open" ref="panelEl" class="select-panel" :style="panelStyle">
        <div v-if="searchable" class="select-search">
          <input
            ref="searchEl"
            v-model="search"
            type="search"
            class="select-search-input"
            :placeholder="t('widget.filterValue')"
            @click.stop
            @keydown.stop
          />
        </div>
        <div class="select-options">
          <button
            v-for="opt in filteredOptions"
            :key="opt.value"
            type="button"
            class="select-option"
            :class="{ active: isSelected(opt.value) }"
            @click="pick(opt)"
          >
            <span v-if="multiple" class="check" :class="{ on: isSelected(opt.value) }">
              <SvgIcon v-if="isSelected(opt.value)" name="check" :size="10" />
            </span>
            <span class="truncate">{{ opt.label }}</span>
          </button>
          <div v-if="!filteredOptions.length" class="empty">{{ t('widget.empty') }}</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.select-box {
  width: 100%;
}
.select-trigger {
  display: flex;
  width: 100%;
  min-height: 32px;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--line);
  background: #fff;
  padding: 4px 8px;
  text-align: left;
  font: inherit;
  font-size: 0.875rem;
  color: var(--ink);
  cursor: pointer;
  box-sizing: border-box;
  overflow: hidden;
}
.select-box.bare .select-trigger {
  min-height: 28px;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0 2px;
  box-shadow: none;
}
.select-trigger:hover:not(.disabled) {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
}
.select-box.bare .select-trigger:hover:not(.disabled) {
  border-color: transparent;
}
.select-trigger:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent) 35%, transparent);
  outline-offset: 0;
  border-color: var(--accent);
}
.select-box.bare .select-trigger:focus-visible {
  outline: none;
  border-color: transparent;
}
.select-trigger.disabled,
.select-box.disabled .select-trigger {
  cursor: not-allowed;
  background: #eef1f4;
  color: var(--muted);
}
.select-box.bare.disabled .select-trigger {
  background: transparent;
}
.placeholder {
  flex: 1;
  min-width: 0;
  color: var(--muted);
}
.value {
  flex: 1;
  min-width: 0;
}
.tags {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}
.tag {
  display: inline-flex;
  flex: 0 0 auto;
  max-width: 100%;
  min-width: 0;
  align-items: center;
  gap: 2px;
  border-radius: var(--radius-sm);
  background: #eef6f3;
  padding: 1px 6px;
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--accent);
  white-space: nowrap;
}
.tag-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag-x {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: color-mix(in srgb, var(--accent) 55%, #fff);
  line-height: 1;
  cursor: pointer;
  padding: 0;
  font: inherit;
  user-select: none;
}
.tag-x:hover {
  color: var(--accent);
}
.trailing {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 2px;
  color: var(--muted);
}
.clear-btn {
  display: inline-flex;
  height: 16px;
  width: 16px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--radius-pill);
  background: transparent;
  font-size: 12px;
  line-height: 1;
  color: var(--muted);
  cursor: pointer;
  padding: 0;
}
.clear-btn:hover {
  background: color-mix(in srgb, var(--line) 60%, #fff);
  color: var(--ink);
}
.chevron {
  transition: transform 0.15s ease;
}
.chevron.open {
  transform: rotate(180deg);
}
</style>

<style>
.select-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--radius-lg);
  border: 1px solid var(--line, #e2e6eb);
  background: var(--panel, #ffffff);
  box-shadow: var(--shadow, 0 12px 40px rgba(40, 30, 10, 0.08));
  padding: 4px;
}
.select-search {
  flex-shrink: 0;
  padding: 4px;
  border-bottom: 1px solid var(--line, #f0ebe3);
}
.select-search-input {
  width: 100%;
  height: 28px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-md);
  padding: 0 8px;
  font: inherit;
  font-size: 0.8125rem;
  background: #fff;
  color: var(--ink, #1c1914);
  box-sizing: border-box;
  outline: none;
}
.select-search-input:focus {
  border-color: var(--accent, #0f6a5a);
}
.select-options {
  overflow: auto;
  min-height: 0;
  flex: 1;
}
.select-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  padding: 7px 8px;
  text-align: left;
  font: inherit;
  font-size: 0.8125rem;
  color: var(--ink, #1c1914);
  cursor: pointer;
}
.select-option:hover {
  background: #f3f8f5;
}
.select-option.active {
  background: #eef6f3;
  color: var(--accent, #0f6a5a);
}
.select-option .check {
  display: inline-flex;
  height: 14px;
  width: 14px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-xs);
  border: 1px solid var(--line, #e2e6eb);
  background: #fff;
  color: #fff;
}
.select-option .check.on {
  border-color: var(--accent, #0f6a5a);
  background: var(--accent, #0f6a5a);
}
.select-panel .empty {
  padding: 12px 8px;
  text-align: center;
  font-size: 0.75rem;
  color: var(--muted, #6b6458);
}
</style>
