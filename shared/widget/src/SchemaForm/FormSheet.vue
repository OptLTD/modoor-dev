<script setup lang="ts">
/**
 * 表单内嵌 ITEMS 表格：jspreadsheet 交互，对齐 duolali SheetForm。
 * 行数据写入 props.values（按 field 名），供父级 buildPayload 直接读取。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import jspreadsheet from 'jspreadsheet-ce'
import type { FormMode, ReferDict, SchemaField } from '@modoor/hooks'
import {
  convertReferValue,
  dateTimeKind,
  editableMode,
  isOnlyDate,
  isRequired,
} from '@modoor/hooks'
import {
  fieldSelectOptions,
  isDateField,
  isNumericFormField,
  isOptionalField,
  isRelationField,
} from './fieldKinds'
import 'jsuites/dist/jsuites.css'
import 'jspreadsheet-ce/dist/jspreadsheet.css'

const ADD = '+'
const REMOVE = '−'

const props = defineProps<{
  title: string
  action: FormMode
  refers?: ReferDict
  fields: SchemaField[]
  values: Record<string, string>[]
  editable?: (field: SchemaField) => boolean
  /** 表格宽度，默认铺满 */
  tableWidth?: string
}>()

const host = ref<HTMLDivElement | null>(null)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let worksheet: any = null
let syncing = false
let muteUntil = 0

function fieldEditable(f: SchemaField) {
  if (editableMode(f) === 'NEVER') return false
  return props.editable ? props.editable(f) : true
}

const canMutate = computed(() => props.fields.some((f) => fieldEditable(f)))

function labelOf(f: SchemaField) {
  const label = String(f.label || f.field || '')
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean)
    .join('')
  return isRequired(f) ? `*${label}` : label
}

function isDropdown(f: SchemaField) {
  return isRelationField(f) || isOptionalField(f)
}

function normalizeDropdown(f: SchemaField, val: string) {
  const s = String(val ?? '').trim()
  if (!s) return ''
  const opts = fieldSelectOptions(f, props.refers)
  if (opts.some((o) => o.value === s)) return s
  const byLabel = opts.find((o) => o.label === s || o.label.trim() === s)
  return byLabel?.value ?? s
}

function dropdownSource(f: SchemaField, extras: string[] = []) {
  const map = new Map<string, string>()
  for (const o of fieldSelectOptions(f, props.refers)) {
    if (o.value) map.set(o.value, o.label || o.value)
  }
  for (const raw of extras) {
    const s = String(raw ?? '').trim()
    if (!s || map.has(s)) continue
    const label = convertReferValue(f, s, props.refers) || s
    map.set(s, label)
  }
  return [...map.entries()].map(([id, name]) => ({ id, name }))
}

function colWidth(f: SchemaField) {
  const w = Number(f.width || f.extra?.width || 0)
  if (w > 0) return w
  if (isRelationField(f)) return 160
  if (isOptionalField(f)) return 120
  if (isNumericFormField(f)) return 110
  if (isDateField(f)) return 140
  return 140
}

function emptyRow(): Record<string, string> {
  const row: Record<string, string> = {}
  for (const f of props.fields) row[f.field] = ''
  return row
}

function ensureRows() {
  if (!props.values.length && canMutate.value) {
    props.values.push(emptyRow())
  }
}

function rowsToMatrix(): string[][] {
  ensureRows()
  const rows = props.values.length ? props.values : [emptyRow()]
  return rows.map((row, ri) => {
    // 下拉列存 value，jspreadsheet 用 source 显示 name
    const cells = props.fields.map((f) => String(row[f.field] ?? ''))
    if (!canMutate.value) return cells
    const symbol = ri === rows.length - 1 ? ADD : REMOVE
    return [symbol, ...cells]
  })
}

function buildColumns() {
  const extrasByField = new Map<string, string[]>()
  for (const f of props.fields) {
    if (!isDropdown(f)) continue
    extrasByField.set(
      f.field,
      props.values.map((r) => String(r[f.field] ?? '')).filter(Boolean),
    )
  }
  const dataCols = props.fields.map((f) => {
    const title = labelOf(f)
    const width = colWidth(f)
    const readOnly = !fieldEditable(f)
    if (isDropdown(f)) {
      return {
        type: 'dropdown' as const,
        title,
        width,
        readOnly,
        source: dropdownSource(f, extrasByField.get(f.field) || []),
        autocomplete: true,
      }
    }
    if (isNumericFormField(f)) {
      return { type: 'numeric' as const, title, width, readOnly, align: 'right' as const }
    }
    if (isDateField(f)) {
      const kind = dateTimeKind(f)
      if (kind === 'ONLYMONTH') {
        return { type: 'text' as const, title, width, readOnly }
      }
      const onlyDate = kind === 'ONLYDATE' || isOnlyDate(f)
      return {
        type: 'calendar' as const,
        title,
        width,
        readOnly,
        options: {
          format: onlyDate ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH24:MI',
          ...(onlyDate ? {} : { time: true as const }),
          position: true as const,
        },
      }
    }
    return { type: 'text' as const, title, width, readOnly }
  })
  if (!canMutate.value) return dataCols
  return [
    {
      type: 'text' as const,
      title: '',
      width: 52,
      readOnly: true,
      align: 'center' as const,
    },
    ...dataCols,
  ]
}

function writeBackFromSheet() {
  if (!worksheet || typeof worksheet.getData !== 'function') return
  muteUntil = Date.now() + 350
  const raw = (worksheet.getData(false, true) as unknown[][]) || []
  const offset = canMutate.value ? 1 : 0
  const next: Record<string, string>[] = []
  for (const cells of raw) {
    const row = emptyRow()
    let filled = false
    props.fields.forEach((f, i) => {
      let v = String(cells[i + offset] ?? '').trim()
      if (isDropdown(f) && v) v = normalizeDropdown(f, v)
      row[f.field] = v
      if (v) filled = true
    })
    // 保留空行以便继续编辑；全空且多行时仍写入，保存时由父级过滤
    if (filled || next.length === 0) next.push(row)
    else next.push(row)
  }
  if (!next.length) next.push(emptyRow())
  syncing = true
  props.values.splice(0, props.values.length, ...next)
  syncing = false
  refreshActionSymbols()
}

function refreshActionSymbols() {
  if (!canMutate.value || !worksheet) return
  const data = (worksheet.getData(false, true) as unknown[][]) || []
  data.forEach((_, ri) => {
    const symbol = ri === data.length - 1 ? ADD : REMOVE
    if (worksheet.getValueFromCoords?.(0, ri) !== symbol) {
      worksheet.setValueFromCoords?.(0, ri, symbol, true)
    }
  })
  worksheet.updateTable?.()
}

function handleActionClick(rowIndex: number) {
  if (!worksheet || !canMutate.value) return
  const data = (worksheet.getData(false, true) as unknown[][]) || []
  const symbol = String(data[rowIndex]?.[0] ?? '')
  if (symbol === ADD) {
    const prev = worksheet.options?.allowInsertRow
    if (worksheet.options) worksheet.options.allowInsertRow = true
    worksheet.insertRow?.(1, data.length - 1, false)
    if (worksheet.options) worksheet.options.allowInsertRow = prev
    writeBackFromSheet()
    return
  }
  if (symbol === REMOVE) {
    if (data.length <= 1) return
    worksheet.deleteRow?.(rowIndex, 1)
    writeBackFromSheet()
  }
}

function mountGrid() {
  destroyGrid()
  const el = host.value
  if (!el || !props.fields.length) return
  ensureRows()
  const columns = buildColumns()
  const data = rowsToMatrix()
  const width = props.tableWidth || '100%'
  const created = jspreadsheet(el, {
    worksheets: [
      {
        data,
        columns,
        allowInsertRow: false,
        allowManualInsertRow: false,
        allowDeleteRow: false,
        allowInsertColumn: false,
        allowDeleteColumn: false,
        columnDrag: false,
        rowDrag: false,
        tableOverflow: true,
        tableWidth: width,
        freezeColumns: canMutate.value ? 1 : 0,
        defaultColAlign: 'left',
        onbeforechange(
          _instance: unknown,
          _cell: HTMLElement,
          x: number | string,
          _y: number | string,
          value: unknown,
        ) {
          const col = Number(x)
          if (canMutate.value && col === 0) return false
          const fi = canMutate.value ? col - 1 : col
          const f = props.fields[fi]
          if (!f || !isDropdown(f)) return undefined
          return normalizeDropdown(f, String(value ?? ''))
        },
        onchange() {
          if (syncing) return
          writeBackFromSheet()
        },
        updateTable(
          _instance: unknown,
          cell: HTMLElement,
          x: number,
          y: number,
          _val: unknown,
        ) {
          if (!canMutate.value || x !== 0) return
          const data = (worksheet?.getData?.(false, true) as unknown[][]) || []
          const symbol = y === data.length - 1 ? ADD : REMOVE
          cell.innerHTML = ''
          cell.className = 'form-sheet-action'
          const btn = document.createElement('button')
          btn.type = 'button'
          btn.className =
            symbol === ADD ? 'form-sheet-btn form-sheet-add' : 'form-sheet-btn form-sheet-remove'
          btn.textContent = symbol === ADD ? '追加' : '删除'
          btn.onclick = (e) => {
            e.preventDefault()
            e.stopPropagation()
            handleActionClick(y)
          }
          cell.appendChild(btn)
        },
      },
    ],
  })
  worksheet = Array.isArray(created) ? created[0] : created
  nextTick(() => {
    syncLayout()
    refreshActionSymbols()
  })
}

function syncLayout() {
  const el = host.value
  if (!el || !worksheet?.content) return
  const parent = el.parentElement
  if (!parent) return
  const w = Math.max(parent.clientWidth || el.clientWidth, 320)
  const content = worksheet.content as HTMLElement
  content.style.width = `${w}px`
  content.style.maxWidth = '100%'
}

function destroyGrid() {
  if (host.value) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      jspreadsheet.destroy(host.value as any)
    } catch {
      /* ignore */
    }
    host.value.innerHTML = ''
  }
  worksheet = null
}

function reloadFromProps() {
  if (Date.now() < muteUntil) return
  if (syncing) return
  mountGrid()
}

onMounted(() => {
  mountGrid()
  window.addEventListener('resize', syncLayout)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncLayout)
  destroyGrid()
})

watch(
  () => [props.fields.map((f) => f.uukey).join('|'), canMutate.value, props.refers] as const,
  () => reloadFromProps(),
)

watch(
  () => props.values,
  () => {
    if (syncing) return
    if (Date.now() < muteUntil) return
    reloadFromProps()
  },
  { deep: true },
)
</script>

<template>
  <section class="form-sheet">
    <header class="form-sheet-head">
      <strong>{{ title }}</strong>
    </header>
    <div class="form-sheet-body">
      <div ref="host" class="form-sheet-host" />
    </div>
  </section>
</template>

<style scoped>
.form-sheet {
  min-width: 0;
  width: 100%;
}
.form-sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  padding: 0 2px;
}
.form-sheet-head strong {
  font-size: 0.9rem;
  font-weight: 600;
}
.form-sheet-body {
  width: 100%;
  min-height: 120px;
  overflow: auto;
}
.form-sheet-host {
  width: 100%;
  min-height: 96px;
}
.form-sheet :deep(.jss_worksheet > thead > tr > td),
.form-sheet :deep(.jexcel > thead > tr > td) {
  background: #eef1f4;
  color: var(--muted, #6b6458);
  font-weight: 600;
  font-size: 13px !important;
  text-align: center !important;
}
.form-sheet :deep(.jss_worksheet > tbody > tr > td),
.form-sheet :deep(.jexcel > tbody > tr > td) {
  font-size: 13px !important;
}
.form-sheet :deep(.form-sheet-action) {
  text-align: center;
  padding: 0 !important;
}
.form-sheet :deep(.form-sheet-btn) {
  border: 0;
  background: none;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  padding: 2px 4px;
  color: var(--accent, #0f6a5a);
}
.form-sheet :deep(.form-sheet-remove) {
  color: var(--danger, #a33b2b);
}
</style>
