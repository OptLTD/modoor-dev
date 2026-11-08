<script setup lang="ts">
/**
 * 公式字典：发站 / 到站 → 运价。
 * 存 base_cfg · type=formula.<rule_uukey>，不写进公式 config。
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { appToast, get as httpGet, put as httpPut } from '@modoor/hooks'

type Spreadsheet = typeof import('jspreadsheet-ce').default

type DictRow = {
  depart: string
  arrive: string
  value: string
}

type Worksheet = {
  getData: () => unknown[][]
  insertRow: (count?: number) => void
  setStyle: (style: Record<string, string>) => void
  resetStyle: (cells: Record<string, true>) => void
  content?: HTMLElement
}

const props = defineProps<{
  rule: string
  ruleLabel: string
  formula: string
}>()

const emit = defineEmits<{
  close: []
  saved: [payload: { match: string[] }]
}>()

const MATCH_FIELDS = ['basic.depot', 'basic.dest']
const VALUE_FIELD = 'dictValue'
const TOKEN = '{{DICT_VALUE}}'
const MIN_ROWS = 12
const DUP_COLOR = '#fff1f0'

let spreadsheet: Spreadsheet | null = null
let worksheet: Worksheet | null = null
let resizeObserver: ResizeObserver | null = null
let painted: Record<string, true> = {}

const host = ref<HTMLDivElement | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')

const headers = ['发站', '到站', '运价']

async function loadSpreadsheet() {
  if (spreadsheet) return spreadsheet
  await Promise.all([
    import('jsuites/dist/jsuites.css'),
    import('jspreadsheet-ce/dist/jspreadsheet.css'),
  ])
  const mod = await import('jspreadsheet-ce')
  spreadsheet = mod.default
  return spreadsheet
}

function emptyRow(): DictRow {
  return { depart: '', arrive: '', value: '' }
}

function isEmpty(row: DictRow): boolean {
  return !row.depart.trim() && !row.arrive.trim() && !row.value.trim()
}

function normalizeRows(raw: unknown): DictRow[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((item) => {
      const row = item as Record<string, unknown>
      return {
        depart: String(row[MATCH_FIELDS[0]] ?? row.depart ?? '').trim(),
        arrive: String(row[MATCH_FIELDS[1]] ?? row.arrive ?? '').trim(),
        value: String(row[VALUE_FIELD] ?? row.value ?? '').trim(),
      }
    })
    .filter((row) => !isEmpty(row))
}

function matrixFromRows(rows: DictRow[]): string[][] {
  const data = rows.map((row) => [row.depart, row.arrive, row.value])
  while (data.length < MIN_ROWS) data.push(['', '', ''])
  return data
}

function readRows(): DictRow[] {
  const data = (worksheet?.getData?.() as unknown[][]) || []
  return data.map((line) => ({
    depart: String(line?.[0] ?? '').trim(),
    arrive: String(line?.[1] ?? '').trim(),
    value: String(line?.[2] ?? '').trim(),
  }))
}

function normStation(value: string): string {
  return value
    .replace(/\s+/g, '')
    .replace(/\(/g, '（')
    .replace(/\)/g, '）')
}

function pairKey(row: DictRow): string {
  return `${normStation(row.depart)}\t${normStation(row.arrive)}`
}

function duplicateKeys(rows: DictRow[]): Set<string> {
  const seen = new Set<string>()
  const dup = new Set<string>()
  for (const row of rows) {
    if (!row.depart || !row.arrive) continue
    const key = pairKey(row)
    if (seen.has(key)) dup.add(key)
    seen.add(key)
  }
  return dup
}

function paintDuplicates(rows: DictRow[]) {
  if (!worksheet) return
  if (Object.keys(painted).length) worksheet.resetStyle(painted)
  painted = {}
  const dup = duplicateKeys(rows)
  if (!dup.size) return
  const style: Record<string, string> = {}
  rows.forEach((row, index) => {
    if (!row.depart || !row.arrive || !dup.has(pairKey(row))) return
    for (let col = 0; col < 3; col++) {
      const name = `${String.fromCharCode(65 + col)}${index + 1}`
      style[name] = `background-color: ${DUP_COLOR}`
      painted[name] = true
    }
  })
  worksheet.setStyle(style)
}

function relayout() {
  const el = host.value
  const content = worksheet?.content
  if (!el || !content) return
  const width = el.clientWidth
  if (width < 80) return
  content.style.width = `${width}px`
  content.style.maxWidth = '100%'
  const height = el.clientHeight
  if (height > 0) {
    content.style.height = `${height}px`
    content.style.maxHeight = `${height}px`
  }
}

function destroyGrid() {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (host.value) {
    try {
      spreadsheet?.destroy(host.value)
    } catch {
      /* ignore */
    }
    host.value.innerHTML = ''
  }
  worksheet = null
  painted = {}
}

async function mountGrid(rows: DictRow[]) {
  const jspreadsheet = await loadSpreadsheet()
  destroyGrid()
  const el = host.value
  if (!el) return
  const created = jspreadsheet(el, {
    worksheets: [
      {
        data: matrixFromRows(rows),
        columns: [
          { title: headers[0], align: 'center', width: 240, type: 'text' },
          { title: headers[1], align: 'center', width: 240, type: 'text' },
          { title: headers[2], align: 'center', width: 120, type: 'number' },
        ],
        minDimensions: [3, MIN_ROWS],
        allowInsertRow: true,
        allowManualInsertRow: true,
        allowDeleteRow: true,
        allowInsertColumn: false,
        allowDeleteColumn: false,
        columnDrag: false,
        columnSorting: false,
        rowDrag: false,
        tableOverflow: true,
        tableWidth: '100%',
        tableHeight: '100%',
        defaultColAlign: 'center',
        onchange() {
          paintDuplicates(readRows())
        },
      },
    ],
  })
  worksheet = created[0] as Worksheet
  paintDuplicates(readRows())
  nextTick(relayout)
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => relayout())
    resizeObserver.observe(el)
  }
}

function appendFiveRows() {
  if (worksheet?.insertRow) {
    worksheet.insertRow(5)
    return
  }
  const rows = readRows()
  void mountGrid([...rows, ...Array.from({ length: 5 }, emptyRow)])
}

async function loadDict() {
  loading.value = true
  error.value = ''
  try {
    const res = await httpGet<{
      dict?: { rows?: unknown }
    }>(`/api/fleet/formula-dict?rule=${encodeURIComponent(props.rule)}`)
    await nextTick()
    await mountGrid(normalizeRows(res.dict?.rows))
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载公式字典失败'
    await nextTick()
    await mountGrid([])
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (saving.value) return
  const allRows = readRows()
  const rows = allRows.filter((row) => !isEmpty(row))
  const dup = duplicateKeys(allRows)
  if (dup.size) {
    paintDuplicates(allRows)
    appToast('存在重复的发站-到站，已高亮，不允许保存', 'error')
    return
  }
  for (const row of rows) {
    if (!row.depart || !row.arrive) {
      appToast('发站、到站不能为空', 'error')
      return
    }
    if (!row.value || !Number.isFinite(Number(row.value)) || Number(row.value) < 0) {
      appToast('运价必须是非负数字', 'error')
      return
    }
  }
  saving.value = true
  error.value = ''
  try {
    await httpPut('/api/fleet/formula-dict', {
      rule: props.rule,
      title: `公式字典 · ${props.ruleLabel}`,
      rows: rows.map((row) => ({
        [MATCH_FIELDS[0]]: row.depart,
        [MATCH_FIELDS[1]]: row.arrive,
        [VALUE_FIELD]: row.value,
      })),
    })
    appToast('保存成功')
    emit('saved', { match: [...MATCH_FIELDS] })
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
    appToast(error.value, 'error')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadDict()
})

onBeforeUnmount(() => {
  destroyGrid()
})
</script>

<template>
  <Teleport to="body">
    <div class="dict-mask" @click.self="emit('close')">
      <section class="dict-sheet" role="dialog" aria-modal="true" aria-label="公式字典">
        <header class="dict-head">
          <div>
            <div class="dict-title">公式字典</div>
            <div class="dict-sub">{{ ruleLabel }} · {{ rule }}</div>
          </div>
          <button type="button" class="close" @click="emit('close')">关闭</button>
        </header>

        <p v-if="!formula.includes(TOKEN)" class="dict-tip">
          当前公式未使用 {{ TOKEN }}，这里的配置暂时不会参与计算。
        </p>
        <p v-if="error" class="dict-error">{{ error }}</p>

        <div v-if="loading" class="dict-loading">加载中…</div>
        <div ref="host" class="dict-grid" />

        <footer class="dict-foot">
          <button type="button" class="btn" @click="appendFiveRows">新增5行</button>
          <button type="button" class="btn primary" :disabled="saving || loading" @click="handleSave">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.dict-mask {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: #1c191766;
}
.dict-sheet {
  width: min(920px, 96vw);
  height: min(720px, 88vh);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 12px;
  background: var(--panel, #fff);
  color: var(--ink, #1c1914);
  box-shadow: 0 18px 48px #1c191733;
}
.dict-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 14px 16px 10px;
}
.dict-title {
  font-size: 16px;
  font-weight: 700;
}
.dict-sub {
  margin-top: 3px;
  color: var(--muted, #6b6458);
  font-size: 12px;
}
.close {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0 4px;
}
.dict-tip,
.dict-error {
  margin: 0 16px 8px;
  font-size: 12px;
  line-height: 1.45;
}
.dict-tip {
  color: var(--muted, #6b6458);
}
.dict-error {
  color: var(--danger, #a33b2b);
}
.btn {
  height: 34px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  background: #fff;
  color: var(--ink, #1c1914);
  padding: 0 14px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn.primary {
  border-color: var(--accent, #0f6a5a);
  background: var(--accent, #0f6a5a);
  color: #fff;
  font-weight: 600;
}
.dict-loading {
  margin: 0 16px 8px;
  color: var(--muted, #6b6458);
  font-size: 12px;
}
.dict-grid {
  flex: 1;
  min-height: 0;
  width: auto;
  margin: 0 16px;
  overflow: hidden;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
}
.dict-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  padding: 12px 16px;
}
.dict-grid :deep(table td),
.dict-grid :deep(table th),
.dict-grid :deep(.jss_worksheet td),
.dict-grid :deep(.jss_worksheet th),
.dict-grid :deep(.jexcel td),
.dict-grid :deep(.jexcel th) {
  font-size: 12px !important;
  text-align: center !important;
}

</style>
