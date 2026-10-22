<script setup lang="ts">
/**
 * Date range picker — presets, start/end inputs, and a linked two-month calendar.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getTermStart, rangeLastNMonths, useI18n } from '@modoor/hooks'
import Dropdown from '../Dropdown/Dropdown.vue'
import SvgIcon from '../SvgIcon/SvgIcon.vue'

const props = withDefaults(
  defineProps<{
    start?: string
    end?: string
    placeholder?: string
    /** 展示用短年份：2026-07-01 → 26-07-01 */
    shortYear?: boolean
    /** 只填了一端时，另一端的展示文案 */
    openLabel?: string
  }>(),
  {
    start: '',
    end: '',
    placeholder: '',
    shortYear: true,
    openLabel: '…',
  },
)

const emit = defineEmits<{
  'update:start': [string]
  'update:end': [string]
  change: [payload: { start: string; end: string }]
}>()

const { t, locale } = useI18n()

const hasValue = computed(() => !!shownStart.value || !!shownEnd.value)
const placeholderText = computed(() => props.placeholder || t('widget.dateRangePh'))

function formatDisplay(v: string) {
  if (!v || v === '…') return props.openLabel || '…'
  if (props.shortYear && /^\d{4}-\d{2}-\d{2}/.test(v)) return v.slice(2, 10)
  return v
}

const display = computed(() => {
  if (!hasValue.value) return ''
  const s = formatDisplay(shownStart.value || '')
  const e = formatDisplay(shownEnd.value || '')
  return `${s} ~ ${e}`
})

/** 只点了起点、还没点终点时记在本地，避免半截区间触发筛选并关掉弹层。 */
const pending = ref<string | null>(null)
const draft = ref<{ start: string; end: string } | null>(null)

function selection() {
  if (pending.value != null) return { start: pending.value, end: '' }
  if (draft.value) return draft.value
  return { start: props.start, end: props.end }
}

const shownStart = computed(() => selection().start)
const shownEnd = computed(() => selection().end)

function commit(start: string, end: string) {
  pending.value = null
  draft.value = { start, end }
  emit('update:start', start)
  emit('update:end', end)
  emit('change', { start, end })
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

/** 财务期间切日来自系统设置，默认 26。10 月 19 日属于本期 9/26–10/25。 */
function termRange(anchor: Date, previous: boolean) {
  const cut = getTermStart()
  let year = anchor.getFullYear()
  let month = anchor.getMonth()
  if (anchor.getDate() >= cut) month += 1
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
    start: new Date(year, month - 1, cut),
    end: new Date(year, month, cut - 1),
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

/** 左右两个连续月份：先点起点，悬停预览，再点终点。 */
type DayCell = { iso: string; day: number; outside: boolean } | null

const calOpen = ref(false)
const calReady = ref(false)
const triggerEl = ref<HTMLElement | null>(null)
const calEl = ref<HTMLElement | null>(null)
const calStyle = ref<Record<string, string>>({})
const hover = ref<string | null>(null)
const view = ref(new Date(today().getFullYear(), today().getMonth(), 1))

const selecting = computed(() => !!shownStart.value && !shownEnd.value)

const weekdays = computed(() => {
  if (locale.value === 'zh-CN') return ['一', '二', '三', '四', '五', '六', '日']
  return ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
})

function monthStart(iso: string) {
  const [y, m] = iso.split('-').map(Number)
  return new Date(y, (m || 1) - 1, 1)
}

function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

function monthTitle(d: Date) {
  return new Intl.DateTimeFormat(locale.value, { year: 'numeric', month: 'long' }).format(d)
}

function monthCells(cursor: Date, side: 'left' | 'right'): DayCell[] {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
  const lead = (first.getDay() + 6) % 7
  const origin = addDays(first, -lead)
  const cells: DayCell[] = Array.from({ length: 42 }, (_, i) => {
    const date = addDays(origin, i)
    const outside = date.getMonth() !== cursor.getMonth()
    if (outside && side === 'left' && date >= first) return null
    if (outside && side === 'right' && date < first) return null
    return { iso: fmt(date), day: date.getDate(), outside }
  })
  while (cells.length >= 7 && cells.slice(-7).every((cell) => !cell)) cells.splice(-7)
  return cells
}

const panes = computed(() => {
  const left = view.value
  const right = addMonths(left, 1)
  return [
    {
      key: fmt(left),
      title: monthTitle(left),
      cells: monthCells(left, 'left'),
      prev: true,
      next: false,
    },
    {
      key: fmt(right),
      title: monthTitle(right),
      cells: monthCells(right, 'right'),
      prev: false,
      next: true,
    },
  ]
})

function bounds(): [string, string] {
  let a = shownStart.value
  let b = shownEnd.value
  if (a && !b && hover.value) b = hover.value
  if (!a && b && hover.value) a = hover.value
  if (!a || !b) {
    if (a) return [a, a]
    if (b) return [b, b]
    return ['', '']
  }
  return a <= b ? [a, b] : [b, a]
}

const activeRange = computed((): [string, string] => {
  void hover.value
  return bounds()
})

function isToday(iso: string) {
  return iso === fmt(today())
}

function dayClass(iso: string, index: number) {
  const [a, b] = activeRange.value
  const has = !!(a && b)
  const isStart = has && iso === a
  const isEnd = has && iso === b
  return {
    'is-start': isStart && iso !== b,
    'is-end': isEnd && iso !== a,
    'is-single': isStart && isEnd,
    'in-range': has && iso > a && iso < b,
    'is-today': isToday(iso),
    'week-start': index % 7 === 0,
    'week-end': index % 7 === 6,
  }
}

function shiftMonth(n: number) {
  view.value = addMonths(view.value, n)
}

function pick(iso: string) {
  hover.value = null
  const cur = selection()
  if (cur.start && !cur.end) {
    if (iso < cur.start) commit(iso, cur.start)
    else commit(cur.start, iso)
    calOpen.value = false
    return
  }
  pending.value = iso
}

function editStart(v: string) {
  const end = pending.value != null ? '' : shownEnd.value
  pending.value = null
  if (end && v && v > end) commit(end, v)
  else commit(v, end || '')
}

function editEnd(v: string) {
  const start = shownStart.value
  pending.value = null
  if (start && v && v < start) commit(v, start)
  else commit(start || '', v)
}

function placeCal() {
  const anchor = triggerEl.value
  const pop = calEl.value
  if (!anchor || !pop) return
  const rect = anchor.getBoundingClientRect()
  const margin = 8
  const width = pop.offsetWidth
  const height = pop.offsetHeight
  let left = rect.left + rect.width / 2 - width / 2
  left = Math.max(margin, Math.min(left, window.innerWidth - width - margin))
  const spaceBelow = window.innerHeight - rect.bottom - margin
  const spaceAbove = rect.top - margin
  const top =
    spaceBelow >= height || spaceBelow >= spaceAbove
      ? Math.min(rect.bottom + 6, window.innerHeight - height - margin)
      : Math.max(margin, rect.top - height - 6)
  calStyle.value = {
    position: 'fixed',
    zIndex: 'calc(var(--z-pop, 10120) + 20)',
    left: `${left}px`,
    top: `${Math.max(margin, top)}px`,
  }
}

function onCalDoc(event: Event) {
  const node = event.target as Node | null
  if (!node) return
  if (calEl.value?.contains(node) || triggerEl.value?.contains(node)) return
  calOpen.value = false
}

function bindCal() {
  window.addEventListener('scroll', placeCal, true)
  window.addEventListener('resize', placeCal)
  document.addEventListener('pointerdown', onCalDoc)
}

function unbindCal() {
  window.removeEventListener('scroll', placeCal, true)
  window.removeEventListener('resize', placeCal)
  document.removeEventListener('pointerdown', onCalDoc)
}

async function openCalendar(dropdownOpen: boolean, toggleDropdown: () => void) {
  if (calOpen.value) {
    calOpen.value = false
    return
  }
  if (dropdownOpen) toggleDropdown()
  const iso = shownStart.value || shownEnd.value
  view.value = iso && /^\d{4}-\d{2}-\d{2}/.test(iso)
    ? monthStart(iso)
    : new Date(today().getFullYear(), today().getMonth(), 1)
  calReady.value = false
  calOpen.value = true
  await nextTick()
  placeCal()
  calReady.value = true
}

function openPresets(toggleDropdown: () => void) {
  if (calOpen.value) calOpen.value = false
  toggleDropdown()
}

watch(calOpen, (open) => {
  if (open) bindCal()
  else {
    unbindCal()
    hover.value = null
    pending.value = null
    calReady.value = false
  }
})

watch(
  () => [props.start, props.end] as const,
  ([s, e]) => {
    if (draft.value && draft.value.start === s && draft.value.end === e) draft.value = null
    if (!calOpen.value) return
    const shown = new Set(
      panes.value.flatMap((pane) => pane.cells.flatMap((cell) => (cell ? [cell.iso] : []))),
    )
    if ((s && shown.has(s)) || (e && shown.has(e))) return
    const iso = s || e
    if (iso && /^\d{4}-\d{2}-\d{2}/.test(iso)) view.value = monthStart(iso)
  },
)

onBeforeUnmount(unbindCal)

</script>

<template>
  <Dropdown class="date-range" :min-width="264" :max-width="300" keep-open>
    <template #trigger="{ open, toggle }">
    <div ref="triggerEl" class="dr-trigger" :class="{ on: calOpen }" @click.stop>
      <button
        type="button"
        class="dr-main"
        :aria-expanded="calOpen"
        aria-haspopup="dialog"
        @click="openCalendar(open, toggle)"
      >
        <SvgIcon name="calendar" class="dr-cal" />
        <span v-if="display" class="value tabular-nums truncate">{{ display }}</span>
        <span v-else class="placeholder truncate">{{ placeholderText }}</span>
      </button>
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
        <button
          type="button"
          class="chevron-btn"
          :class="{ open }"
          :aria-expanded="open"
          aria-haspopup="true"
          :title="t('widget.more')"
          @click.stop="openPresets(toggle)"
        >
          <SvgIcon name="chevron-down" class="chevron" :class="{ open }" :size="12" />
        </button>
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
              :value="shownStart"
              @input="editStart(($event.target as HTMLInputElement).value)"
            />
          </label>
          <span class="dr-sep">~</span>
          <label class="dr-field">
            <span class="dr-cap">{{ t('widget.drEnd') }}</span>
            <input
              type="date"
              :value="shownEnd"
              @input="editEnd(($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
  </Dropdown>
  <Teleport to="body">
          <div
            v-if="calOpen"
            ref="calEl"
            class="dr-cal-pop"
            :class="{ ready: calReady, pending: selecting }"
            :style="calStyle"
            @pointerdown.stop
            @mouseleave="hover = null"
          >
            <section v-for="pane in panes" :key="pane.key" class="dr-month">
              <div class="dr-month-head">
                <button
                  v-if="pane.prev"
                  type="button"
                  class="dr-nav"
                  :aria-label="t('widget.drPrev')"
                  @click="shiftMonth(-1)"
                >
                  <SvgIcon name="chevron-left" :size="14" />
                </button>
                <span v-else class="dr-nav-slot" />
                <span class="dr-month-title">{{ pane.title }}</span>
                <button
                  v-if="pane.next"
                  type="button"
                  class="dr-nav"
                  :aria-label="t('widget.drNext')"
                  @click="shiftMonth(1)"
                >
                  <SvgIcon name="chevron-right" :size="14" />
                </button>
                <span v-else class="dr-nav-slot" />
              </div>
              <div class="dr-weekdays">
                <span v-for="name in weekdays" :key="name">{{ name }}</span>
              </div>
              <div class="dr-grid">
                <template v-for="(cell, i) in pane.cells" :key="`${pane.key}-${i}`">
                  <span v-if="!cell" class="dr-day is-empty" />
                  <span
                    v-else
                    class="dr-day"
                    :class="[dayClass(cell.iso, i), { out: cell.outside }]"
                  >
                    <span class="band" />
                    <button
                      type="button"
                      @mouseenter="hover = cell.iso"
                      @click="pick(cell.iso)"
                    >
                      {{ cell.day }}
                    </button>
                  </span>
                </template>
              </div>
            </section>
          </div>
  </Teleport>
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
  padding: 0 0.15rem;
  box-sizing: border-box;
}
.dr-main {
  display: flex;
  flex: 1;
  min-width: 0;
  height: 100%;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-size: 12px;
  line-height: 1;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.dr-trigger.on .dr-cal {
  color: var(--accent, #0f6a5a);
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
.chevron-btn {
  display: inline-flex;
  height: 16px;
  width: 16px;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--radius-pill);
  padding: 0;
  color: var(--muted, #6b6458);
  background: transparent;
  cursor: pointer;
}
.chevron-btn:hover,
.chevron-btn.open {
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
  flex-shrink: 0;
  color: var(--muted, #a8a29e);
}
.dr-cal-pop {
  position: fixed;
  top: 0;
  left: 0;
  z-index: calc(var(--z-pop, 10120) + 20);
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 10px 12px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-xl, 12px);
  background: var(--panel, #fff);
  box-shadow: var(--shadow, 0 12px 40px rgba(40, 30, 10, 0.12));
  color: var(--ink, #1c1914);
  user-select: none;
  visibility: hidden;
}
.dr-cal-pop.ready {
  visibility: visible;
}
.dr-month-head {
  display: grid;
  grid-template-columns: 28px 1fr 28px;
  align-items: center;
  height: 28px;
  margin-bottom: 4px;
}
.dr-month-title {
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
}
.dr-nav,
.dr-nav-slot {
  width: 28px;
  height: 28px;
}
.dr-nav {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--radius-pill, 999px);
  padding: 0;
  color: var(--ink, #1c1914);
  background: transparent;
  cursor: pointer;
}
.dr-nav:hover {
  background: color-mix(in srgb, var(--ink, #1c1914) 6%, transparent);
}
.dr-weekdays,
.dr-grid {
  display: grid;
  grid-template-columns: repeat(7, 32px);
}
.dr-weekdays span {
  height: 22px;
  font-size: 11px;
  line-height: 22px;
  text-align: center;
  color: var(--muted, #a8a29e);
}
.dr-day {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 32px;
}
.dr-day .band {
  display: none;
  position: absolute;
  top: 2px;
  bottom: 2px;
  left: 0;
  right: 0;
  background: color-mix(in srgb, var(--accent, #0f6a5a) 16%, transparent);
}
.dr-cal-pop.pending .band {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 10%, transparent);
}
.dr-day.in-range .band,
.dr-day.is-start .band,
.dr-day.is-end .band {
  display: block;
}
.dr-day.is-start .band {
  left: 50%;
}
.dr-day.is-end .band {
  right: 50%;
}
.dr-day.is-start.week-end .band,
.dr-day.is-end.week-start .band {
  display: none;
}
.dr-day.week-start.in-range .band {
  border-top-left-radius: 999px;
  border-bottom-left-radius: 999px;
}
.dr-day.week-end.in-range .band {
  border-top-right-radius: 999px;
  border-bottom-right-radius: 999px;
}
.dr-day button {
  position: relative;
  z-index: 1;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--radius-pill, 999px);
  padding: 0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  line-height: 1;
  color: var(--ink, #1c1914);
  background: transparent;
  cursor: pointer;
}
.dr-day button:hover {
  background: color-mix(in srgb, var(--ink, #1c1914) 6%, transparent);
}
.dr-day.is-start button,
.dr-day.is-end button,
.dr-day.is-single button,
.dr-day.is-start button:hover,
.dr-day.is-end button:hover,
.dr-day.is-single button:hover {
  background: var(--accent, #0f6a5a);
  color: #fff;
}
.dr-day.is-today button {
  box-shadow: inset 0 0 0 1px var(--accent, #0f6a5a);
}
.dr-day.is-today.is-start button,
.dr-day.is-today.is-end button,
.dr-day.is-today.is-single button {
  box-shadow: none;
}
.dr-day.out button {
  color: var(--muted, #a8a29e);
}
.dr-day.out.is-start button,
.dr-day.out.is-end button,
.dr-day.out.is-single button,
.dr-day.out.is-start button:hover,
.dr-day.out.is-end button:hover,
.dr-day.out.is-single button:hover {
  color: #fff;
}
@media (max-width: 640px) {
  .dr-cal-pop {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
