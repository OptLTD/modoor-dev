<template>
  <div class="xlsx-preview">
    <p v-if="loading" class="muted">{{ t('doc.previewLoading') }}</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <div class="sheet-bar">
        <div class="sheet-tabs">
          <button
            v-for="(name, i) in sheetNames"
            :key="`${i}-${name}`"
            type="button"
            class="btn"
            :class="{ primary: i === sheetIndex }"
            :disabled="pageLoading"
            @click="selectSheet(i)"
          >
            {{ name }}
          </button>
        </div>
        <div v-if="hasPrev || hasNext || page > 1" class="sheet-pager">
          <button
            type="button"
            class="page-btn"
            :disabled="!hasPrev || pageLoading"
            :aria-label="t('doc.previewPrev')"
            :title="t('doc.previewPrev')"
            @click="selectPage(page - 1)"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path fill="currentColor" d="M10.2 2.6 4.8 8l5.4 5.4.9-.9L6.6 8l4.5-4.5z" />
            </svg>
          </button>
          <button
            type="button"
            class="page-btn"
            :disabled="!hasNext || pageLoading"
            :aria-label="t('doc.previewNext')"
            :title="t('doc.previewNext')"
            @click="selectPage(page + 1)"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
              <path fill="currentColor" d="m5.8 2.6-.9.9L9.4 8l-4.5 4.5.9.9L11.2 8z" />
            </svg>
          </button>
        </div>
      </div>
      <p v-if="pageError" class="error">{{ pageError }}</p>
      <div class="sheet-wrap" :class="{ dimmed: pageLoading }">
        <table v-if="colCount">
          <thead>
            <tr>
              <th class="row-num">1</th>
              <th
                v-for="ci in colIndexes"
                :key="`h-${ci}`"
                class="col-h"
                :class="{ filterable: Boolean(facetOf(ci)) }"
              >
                <span class="col-title">{{ header[ci] || '' }}</span>
                <button
                  v-if="facetOf(ci)"
                  type="button"
                  class="filter-btn"
                  :class="{ on: isFilterOn(ci), open: openFilter === ci }"
                  :disabled="pageLoading"
                  :aria-label="facetOf(ci)?.name || ''"
                  @click.stop="toggleFilter(ci, $event)"
                >
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M2 3.5h12l-4.2 5.2V13l-3.6-1.6V8.7z"
                    />
                  </svg>
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in rows" :key="rowNumbers[ri] ?? ri">
              <th class="row-num">{{ rowNumbers[ri] ?? startRow + ri }}</th>
              <td v-for="ci in colIndexes" :key="ci">{{ row[ci] || '' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted empty">{{ t('doc.emptyDoc') }}</p>
      </div>
      <Teleport to="body">
        <div
          v-if="openFacet && openFilter != null"
          ref="panelEl"
          class="xlsx-filter-panel"
          :style="panelStyle"
          @mousedown.stop
        >
          <div class="filter-list">
            <button
              v-for="opt in filterOptions(openFacet)"
              :key="opt.value"
              type="button"
              class="filter-option"
              :class="{ active: openIsChosen(opt.value) }"
              @click="pickOpenValue(opt.value)"
            >
              <span class="check" :class="{ on: openIsChosen(opt.value) }">
                <svg v-if="openIsChosen(opt.value)" width="10" height="10" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M3.5 8.5l3 3 6-6.5"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </span>
              <span class="truncate">{{ opt.label }}</span>
              <span class="count">{{ opt.count }}</span>
            </button>
          </div>
          <div class="filter-foot">
            <button type="button" class="filter-foot-btn" @click="selectAllOpen">
              {{ t('doc.filterAll') }}
            </button>
            <button type="button" class="filter-foot-btn" @click="clearOpen">
              {{ t('doc.filterClear') }}
            </button>
          </div>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getAssetPreview, type ExcelFilter } from '../api/doc'
import { useI18n } from '@modoor/hooks'

const EMPTY = '__empty__'
const props = defineProps<{ assetId: string }>()
const { t } = useI18n()

const loading = ref(false)
const error = ref('')
const pageLoading = ref(false)
const pageError = ref('')
const sheetNames = ref<string[]>([])
const header = ref<string[]>([])
const rows = ref<string[][]>([])
const rowNumbers = ref<number[]>([])
const sheetIndex = ref(0)
const page = ref(1)
const startRow = ref(2)
const hasPrev = ref(false)
const hasNext = ref(false)
const filterCols = ref<ExcelFilter[]>([])
const chosen = ref<Record<number, string[]>>({})
const openFilter = ref<number | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const panelStyle = ref<Record<string, string>>({})
let filterAnchor: HTMLElement | null = null
let facetSeq = 0

const colCount = computed(() => {
  let n = header.value.length
  for (const row of rows.value) n = Math.max(n, row.length)
  return n
})
const colIndexes = computed(() => Array.from({ length: colCount.value }, (_, i) => i))
const filterMap = computed(() => {
  const map = new Map<number, ExcelFilter>()
  for (const f of filterCols.value) map.set(f.col, f)
  return map
})
const openFacet = computed(() =>
  openFilter.value == null ? null : filterMap.value.get(openFilter.value) || null,
)

function facetOf(ci: number) {
  return filterMap.value.get(ci)
}

function isFilterOn(ci: number) {
  return (chosen.value[ci] || []).length > 0
}

function isChosen(ci: number, value: string) {
  return (chosen.value[ci] || []).includes(value)
}

function openIsChosen(value: string) {
  return openFilter.value != null && isChosen(openFilter.value, value)
}

function pickOpenValue(value: string) {
  if (openFilter.value == null) return
  void toggleValue(openFilter.value, value)
}

function clearOpen() {
  if (openFilter.value == null) return
  void onFilter(openFilter.value, [])
}

function selectAllOpen() {
  if (openFilter.value == null || !openFacet.value) return
  const vals = filterOptions(openFacet.value).map((o) => o.value)
  void onFilter(openFilter.value, vals)
}

function filterOptions(f: ExcelFilter) {
  return f.values.map((item) => {
    const v = item.value
    return {
      value: v === '' ? EMPTY : v,
      label: v === '' ? t('doc.filterEmpty') : v,
      count: item.count,
    }
  })
}

function apiFilters(): Record<string, string[]> | undefined {
  const out: Record<string, string[]> = {}
  for (const [col, vals] of Object.entries(chosen.value)) {
    if (!vals?.length) continue
    out[col] = vals.map((v) => (v === EMPTY ? '' : v))
  }
  return Object.keys(out).length ? out : undefined
}

function placePanel(anchor: HTMLElement) {
  const r = anchor.getBoundingClientRect()
  const width = 200
  const maxH = 240
  const left = Math.min(Math.max(8, r.right - width), window.innerWidth - width - 8)
  const spaceBelow = window.innerHeight - r.bottom - 8
  const placeUp = spaceBelow < 140 && r.top > spaceBelow
  panelStyle.value = {
    position: 'fixed',
    left: `${left}px`,
    width: `${width}px`,
    zIndex: '80',
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

async function toggleFilter(ci: number, ev: MouseEvent) {
  const btn = ev.currentTarget as HTMLElement
  if (openFilter.value === ci) {
    closeFilter()
    return
  }
  openFilter.value = ci
  filterAnchor = btn
  await nextTick()
  placePanel(btn)
}

function closeFilter() {
  openFilter.value = null
  filterAnchor = null
}

function onDocPointer(e: Event) {
  const t = e.target as Node
  if (filterAnchor?.contains(t)) return
  if (panelEl.value?.contains(t)) return
  closeFilter()
}

function onScrollOrResize() {
  if (openFilter.value == null || !filterAnchor) return
  placePanel(filterAnchor)
}

onMounted(() => {
  document.addEventListener('mousedown', onDocPointer)
  window.addEventListener('scroll', onScrollOrResize, true)
  window.addEventListener('resize', onScrollOrResize)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocPointer)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})

async function fetchPage(sheet: number, nextPage: number) {
  const preview = await getAssetPreview(props.assetId, {
    sheet,
    page: nextPage,
    filters: apiFilters(),
  })
  applyPreview(preview, sheet, nextPage)
}

function applyPreview(
  preview: Awaited<ReturnType<typeof getAssetPreview>>,
  sheet: number,
  nextPage: number,
) {
  sheetNames.value = preview.sheet_names || []
  sheetIndex.value = preview.sheet ?? sheet
  header.value = preview.header || []
  rows.value = preview.rows || []
  rowNumbers.value = preview.row_numbers || []
  page.value = preview.page || nextPage
  startRow.value = preview.start_row || 2
  hasPrev.value = Boolean(preview.has_prev)
  hasNext.value = Boolean(preview.has_next)
}

async function loadFacets(sheet: number) {
  const seq = ++facetSeq
  try {
    const preview = await getAssetPreview(props.assetId, {
      sheet,
      page: 1,
      facets: true,
    })
    if (seq !== facetSeq) return
    filterCols.value = preview.filters || []
  } catch {
    if (seq !== facetSeq) return
    filterCols.value = []
  }
}

async function load() {
  loading.value = true
  error.value = ''
  pageError.value = ''
  sheetNames.value = []
  header.value = []
  rows.value = []
  rowNumbers.value = []
  sheetIndex.value = 0
  page.value = 1
  filterCols.value = []
  chosen.value = {}
  closeFilter()
  try {
    await fetchPage(0, 1)
    void loadFacets(0)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function selectSheet(i: number) {
  if (i === sheetIndex.value && !pageError.value) return
  pageLoading.value = true
  pageError.value = ''
  chosen.value = {}
  filterCols.value = []
  closeFilter()
  try {
    await fetchPage(i, 1)
    void loadFacets(i)
  } catch (e) {
    pageError.value = e instanceof Error ? e.message : String(e)
  } finally {
    pageLoading.value = false
  }
}

async function selectPage(nextPage: number) {
  if (nextPage < 1) return
  pageLoading.value = true
  pageError.value = ''
  try {
    await fetchPage(sheetIndex.value, nextPage)
  } catch (e) {
    pageError.value = e instanceof Error ? e.message : String(e)
  } finally {
    pageLoading.value = false
  }
}

async function onFilter(col: number, value: string | string[]) {
  chosen.value = {
    ...chosen.value,
    [col]: Array.isArray(value) ? value : value ? [value] : [],
  }
  pageLoading.value = true
  pageError.value = ''
  try {
    await fetchPage(sheetIndex.value, 1)
  } catch (e) {
    pageError.value = e instanceof Error ? e.message : String(e)
  } finally {
    pageLoading.value = false
  }
}

async function toggleValue(col: number, value: string) {
  const cur = chosen.value[col] || []
  const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value]
  await onFilter(col, next)
}

watch(
  () => props.assetId,
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<style scoped>
.xlsx-preview {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sheet-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.sheet-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.sheet-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
}

.sheet-wrap.dimmed {
  opacity: 0.55;
  pointer-events: none;
}

.empty {
  margin: 12px;
}

table {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  font-size: 0.82rem;
}

th,
td {
  border: 1px solid var(--line);
  padding: 4px 8px;
  white-space: nowrap;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #eef1f4;
  font-weight: 600;
}

.col-h.filterable {
  position: sticky;
  top: 0;
  padding-right: 22px;
}

.col-title {
  display: inline-block;
}

.filter-btn {
  position: absolute;
  right: 3px;
  top: 50%;
  transform: translateY(-50%);
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-xs);
  background: transparent;
  color: #8a8174;
  cursor: pointer;
  opacity: 0;
}

.col-h:hover .filter-btn,
.filter-btn.on,
.filter-btn.open {
  opacity: 1;
}

.filter-btn.on,
.filter-btn.open {
  color: var(--accent);
}

.filter-btn:disabled {
  cursor: not-allowed;
}

.row-num {
  position: sticky;
  left: 0;
  z-index: 1;
  box-sizing: border-box;
  width: 3rem;
  min-width: 3rem;
  max-width: 3rem;
  padding: 4px 4px;
  overflow: hidden;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: #6b7280;
  background: #f3eee4;
  user-select: none;
}

thead .row-num {
  z-index: 3;
  background: #efe8db;
}

.sheet-pager {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-left: auto;
}

.page-btn {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  color: inherit;
  cursor: pointer;
}

.page-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>

<style>
.xlsx-filter-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: #fff;
  box-shadow: 0 8px 24px #00000022;
}

.xlsx-filter-panel .filter-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px;
}

.xlsx-filter-panel .filter-foot {
  flex-shrink: 0;
  display: flex;
  border-top: 1px solid var(--line);
  background: #fff;
}

.xlsx-filter-panel .filter-foot-btn {
  flex: 1;
  border: 0;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 0.78rem;
  padding: 8px;
  cursor: pointer;
}

.xlsx-filter-panel .filter-foot-btn + .filter-foot-btn {
  border-left: 1px solid var(--line);
}

.xlsx-filter-panel .filter-foot-btn:hover {
  color: inherit;
  background: #eef1f4;
}

.xlsx-filter-panel .filter-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 0.82rem;
  text-align: left;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  cursor: pointer;
}

.xlsx-filter-panel .filter-option:hover,
.xlsx-filter-panel .filter-option.active {
  background: #eef1f4;
}

.xlsx-filter-panel .filter-option .check {
  width: 14px;
  height: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius-xs);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: #fff;
}

.xlsx-filter-panel .filter-option .check.on {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.xlsx-filter-panel .filter-option .truncate {
  flex: 1;
  min-width: 0;
}

.xlsx-filter-panel .filter-option .count {
  flex-shrink: 0;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  font-size: 0.75rem;
}
</style>
