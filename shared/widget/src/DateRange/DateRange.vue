<script setup lang="ts">
/**
 * Date range picker — presets + start/end inputs (worth DateRange pattern).
 */
import { computed } from 'vue'
import { rangeLastNMonths, useI18n } from '@modoor/hooks'
import Dropdown from '../Dropdown/Dropdown.vue'
import SvgIcon from '../SvgIcon/SvgIcon.vue'

const props = withDefaults(
  defineProps<{
    start?: string
    end?: string
    placeholder?: string
    /** 展示用短年份：2026-07-01 → 26-07-01 */
    shortYear?: boolean
  }>(),
  {
    start: '',
    end: '',
    placeholder: '',
    shortYear: true,
  },
)

const emit = defineEmits<{
  'update:start': [string]
  'update:end': [string]
  change: [payload: { start: string; end: string }]
}>()

const { t } = useI18n()

const hasValue = computed(() => !!props.start || !!props.end)
const placeholderText = computed(() => props.placeholder || t('widget.dateRangePh'))

function formatDisplay(v: string) {
  if (!v || v === '…') return v || '…'
  if (props.shortYear && /^\d{4}-\d{2}-\d{2}/.test(v)) return v.slice(2, 10)
  return v
}

const display = computed(() => {
  if (!hasValue.value) return ''
  const s = formatDisplay(props.start || '…')
  const e = formatDisplay(props.end || '…')
  return `${s} ~ ${e}`
})

function commit(start: string, end: string) {
  emit('update:start', start)
  emit('update:end', end)
  emit('change', { start, end })
}

function setStart(v: string) {
  if (props.end && v && v > props.end) {
    commit(props.end, v)
  } else {
    commit(v, props.end || '')
  }
}

function setEnd(v: string) {
  if (props.start && v && v < props.start) {
    commit(v, props.start)
  } else {
    commit(props.start || '', v)
  }
}

function clear(e?: Event) {
  e?.stopPropagation()
  commit('', '')
}

function pad(n: number) {
  return String(n).padStart(2, '0')
}
function fmt(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function today() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}
function addDays(d: Date, n: number) {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}
function applyPreset(start: Date, end: Date) {
  commit(fmt(start), fmt(end))
}

/** 财务期间：26 日切。10 月 7 日属于本期 9/26–10/25。 */
const TERM_START = 26
function termRange(anchor: Date, previous: boolean) {
  let year = anchor.getFullYear()
  let month = anchor.getMonth()
  if (anchor.getDate() >= TERM_START) month += 1
  if (month > 11) {
    month = 0
    year += 1
  }
  if (previous) {
    month -= 1
    if (month < 0) {
      month = 11
      year -= 1
    }
  }
  return {
    start: new Date(year, month - 1, TERM_START),
    end: new Date(year, month, TERM_START - 1),
  }
}

const presets = computed(() => {
  const t0 = today()
  const y = t0.getFullYear()
  const m = t0.getMonth()
  const weekStartOffset = (t0.getDay() + 6) % 7
  const thisWeekStart = addDays(t0, -weekStartOffset)
  return [
    { label: t('widget.drToday'), run: () => applyPreset(t0, t0) },
    { label: t('widget.drYesterday'), run: () => applyPreset(addDays(t0, -1), addDays(t0, -1)) },
    { label: t('widget.drThisWeek'), run: () => applyPreset(thisWeekStart, t0) },
    {
      label: t('widget.drLastWeek'),
      run: () => applyPreset(addDays(thisWeekStart, -7), addDays(thisWeekStart, -1)),
    },
    {
      label: t('widget.drThisMonth'),
      run: () => applyPreset(new Date(y, m, 1), new Date(y, m + 1, 0)),
    },
    {
      label: t('widget.drLastMonth'),
      run: () => applyPreset(new Date(y, m - 1, 1), new Date(y, m, 0)),
    },
    {
      label: t('widget.drThisTerm'),
      run: () => {
        const r = termRange(t0, false)
        applyPreset(r.start, r.end)
      },
    },
    {
      label: t('widget.drLastTerm'),
      run: () => {
        const r = termRange(t0, true)
        applyPreset(r.start, r.end)
      },
    },
    {
      label: t('widget.drThisYear'),
      run: () => applyPreset(new Date(y, 0, 1), new Date(y, 11, 31)),
    },
    {
      label: t('widget.drLast3Months'),
      run: () => {
        const r = rangeLastNMonths(3)
        commit(r.start, r.end)
      },
    },
    {
      label: t('widget.drLast6Months'),
      run: () => {
        const r = rangeLastNMonths(6)
        commit(r.start, r.end)
      },
    },
    // { label: t('widget.drLast30'), run: () => applyPreset(addDays(t0, -29), t0) },
  ]
})

const presetRows = computed(() => {
  const all = presets.value
  const size = Math.ceil(all.length / 2)
  return [all.slice(0, size), all.slice(size, size * 2), all.slice(size * 2)]
})

</script>

<template>
  <Dropdown class="date-range" :min-width="264" :max-width="300" keep-open>
    <template #trigger="{ open, toggle }">
    <div
      class="dr-trigger"
      role="button"
      tabindex="0"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
    >
      <SvgIcon name="calendar" class="dr-cal" />
      <span v-if="display" class="value tabular-nums truncate">{{ display }}</span>
      <span v-else class="placeholder truncate">{{ placeholderText }}</span>
      <span class="trailing">
        <button
          v-if="hasValue"
          type="button"
          class="clear-btn"
          :title="t('widget.clear')"
          @click.stop="clear"
        >
          ×
        </button>
        <SvgIcon name="chevron-down" class="chevron" :class="{ open }" :size="12" />
      </span>
    </div>
    </template>
        <div class="dr-presets">
          <div v-for="(row, i) in presetRows" :key="i" class="dr-row">
            <button
              v-for="p in row"
              :key="p.label"
              type="button"
              class="dr-preset"
              @click="p.run"
            >
              {{ p.label }}
            </button>
          </div>
        </div>
        <div class="dr-inputs">
          <label class="dr-field">
            <span class="dr-cap">{{ t('widget.drStart') }}</span>
            <input
              type="date"
              :value="start"
              @input="setStart(($event.target as HTMLInputElement).value)"
            />
          </label>
          <span class="dr-sep">~</span>
          <label class="dr-field">
            <span class="dr-cap">{{ t('widget.drEnd') }}</span>
            <input
              type="date"
              :value="end"
              @input="setEnd(($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
  </Dropdown>
</template>

<style scoped>
.date-range {
  width: 100%;
  min-width: 0;
}
.date-range :deep(.dropdown-trigger) {
  display: flex;
  width: 100%;
}
.dr-trigger {
  display: flex;
  width: 100%;
  height: 28px;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  background: transparent;
  padding: 0 0.15rem;
  font-size: 12px;
  line-height: 1;
  color: inherit;
  cursor: pointer;
  box-sizing: border-box;
}
.dr-cal {
  flex-shrink: 0;
  color: var(--muted, #6b6458);
}
.placeholder {
  flex: 1;
  min-width: 0;
  color: var(--muted, #6b6458);
}
.value {
  flex: 1;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.trailing {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.15rem;
  color: var(--muted, #6b6458);
}
.clear-btn {
  display: inline-flex;
  height: 16px;
  width: 16px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--radius-pill);
  padding: 0;
  font-size: 12px;
  line-height: 1;
  color: var(--muted, #6b6458);
  background: transparent;
  cursor: pointer;
}
.clear-btn:hover {
  background: color-mix(in srgb, var(--ink, #1c1914) 6%, transparent);
  color: var(--ink, #1c1914);
}
.chevron {
  transition: transform 0.15s ease;
}
.chevron.open {
  transform: rotate(180deg);
}
</style>

<style>
.dr-presets {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--line, #f0ebe3);
}
.dr-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 0.25rem;
}
.dr-preset {
  border-radius: var(--radius-md);
  border: 1px solid var(--line, #e2e6eb);
  background: var(--panel, #fff);
  padding: 0.2rem 0.5rem;
  font-size: 11px;
  line-height: 1;
  color: var(--muted, #57534e);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.dr-preset:hover {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 10%, transparent);
  border-color: color-mix(in srgb, var(--accent, #0f6a5a) 35%, transparent);
  color: var(--accent, #0f6a5a);
}
.dr-inputs {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding-top: 0.5rem;
}
.dr-field {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 0.25rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--line, #e2e6eb);
  padding: 0.2rem 0.4rem;
}
.dr-cap {
  font-size: 11px;
  color: var(--muted, #a8a29e);
}
.dr-field input {
  width: 100%;
  min-width: 0;
  border: none;
  outline: none;
  font-size: 12px;
  color: inherit;
  background: transparent;
}
.dr-sep {
  color: var(--muted, #a8a29e);
}
</style>
