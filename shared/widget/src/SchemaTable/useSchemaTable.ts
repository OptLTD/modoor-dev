import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  useRecordGateway,
  type SchemaClick,
  type SchemaField,
  type SchemaTable,
  type SearchFacet,
} from '@modoor/hooks'
import { exportRows } from '@modoor/hooks'
import {
  applyStickyOrder,
  displayFieldValue,
  formatNumericDisplay,
  isMultiple,
  isNumericField,
  isSortableField,
  mergeRefers,
  normalizeReferDict,
  pickFieldValue,
  referOptions,
  convertReferValue,
  sortIndexField,
  type ReferDict,
} from '@modoor/hooks'
import {
  defaultOp,
  draftFromDateRange,
  dateRangeFromDraft,
  expandRctToken,
  filterOps,
  isDraftActive,
  needsValue2,
  showValue,
  type FilterDraft,
} from '@modoor/hooks'
import {
  buildListQuery,
  fieldKey,
  mergeListQuery,
  modFromModel,
  viewWidths,
  ACTION_WIDTH_KEY,
  rowUUKey,
  t,
} from '@modoor/hooks'

export const CHECK_W = 40
export const ACTION_MIN = 36
const ACTION_KEY = ACTION_WIDTH_KEY

/**
 * Schema list：加载、列宽/sticky、筛选、排序、选择、导出（供 Workspace 调用）。
 */
export function useSchemaTable(
  props: {
    table: SchemaTable
    using?: string
    actionMin?: number
    /** 隐藏表体时跳过列表拉取（批量 sheet 态） */
    hideBody?: boolean
  },
  options?: {
    onRequestChange?: (req: {
      page: number
      size: number
      query?: Record<string, unknown>
    }) => void
  },
) {
  const gateway = useRecordGateway()
  const rows = ref<Record<string, unknown>[]>([])
  const totals = ref<Record<string, unknown>>({})
  const facets = ref<Record<string, SearchFacet>>({})
  const count = ref(0)
  const page = ref(1)
  const size = ref(100)
  const PAGE_SIZES = [100, 200, 500, 1000] as const
  const error = ref('')
  const loading = ref(false)
  const selectedKeys = ref<string[]>([])
  const order = ref<{ field: string; order: 'asc' | 'desc' } | null>(null)
  const theRefers = ref<ReferDict>({})

  const appliedFilters = reactive<Record<string, FilterDraft>>({})
  const filterDraft = reactive<Record<string, FilterDraft>>({})
  /** request.query 去掉已种子化到 appliedFilters 的 RCT，避免与用户筛选冲突 */
  const baseQuery = reactive<Record<string, unknown>>({})
  const filterOpen = ref<string | null>(null)
  const panelFilterOpen = ref(false)
  const columnOpen = ref(false)
  /** null 表示沿用模型默认顺序 / 默认显隐 */
  const columnOrder = ref<string[] | null>(null)
  const columnHidden = ref<string[] | null>(null)

  const colWidths = reactive<Record<string, number>>({})
  const actionResizeMin = computed(() => Math.max(ACTION_MIN, props.actionMin ?? 48))
  const actionWidth = ref(actionResizeMin.value)

  const fields = computed(() => props.table.fields || [])
  const using = computed(() => props.using || props.table.using || 'default')

  /** 聚合表：others.$digest 存在时，度量列不筛、排序本地做 */
  const digestMeta = computed(() => {
    const raw = props.table.others?.$digest
    return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null
  })
  const isDigestMode = computed(() => !!digestMeta.value)
  /** 原始字段（digest 度量可能改写 fields[].ftype）；筛选交互按此映射 */
  const originMap = computed((): Record<string, SchemaField> => {
    const raw = props.table.origin
    return raw && typeof raw === 'object' ? (raw as Record<string, SchemaField>) : {}
  })
  function fieldForFilter(key: string): SchemaField | undefined {
    const k = String(key || '').trim()
    if (!k) return undefined
    const fromOrigin = originMap.value[k]
    if (fromOrigin) return fromOrigin
    return fields.value.find(
      (f) => fieldKey(f) === k || f.uukey === k || `basic.${f.field}` === k,
    )
  }
  /** 侧栏 FilterPanel：有 filters 声明时只用这些；否则用展示列并优先 origin */
  const panelFilterFields = computed((): SchemaField[] => {
    const keys = props.table.filters || []
    if (keys.length) {
      const out: SchemaField[] = []
      const seen = new Set<string>()
      for (const key of keys) {
        const f = fieldForFilter(String(key))
        if (!f || !isHeaderFilterable(f)) continue
        const fk = fieldKey(f)
        if (seen.has(fk)) continue
        seen.add(fk)
        out.push(f)
      }
      return out
    }
    return fields.value
      .filter((f) => f.shown !== false && f.field && f.field !== 'model' && f.field !== 'state')
      .filter((f) => isHeaderFilterable(f))
      .map((f) => originMap.value[fieldKey(f)] || originMap.value[f.uukey] || f)
  })
  const digestMetricKeys = computed(() => {
    const d = digestMeta.value
    if (!d) return new Set<string>()
    const keys = new Set<string>()
    for (const c of (Array.isArray(d.count_fn) ? d.count_fn : []) as { index?: string }[]) {
      if (c?.index) keys.add(String(c.index))
    }
    for (const a of (Array.isArray(d.append) ? d.append : []) as { field?: string }[]) {
      if (a?.field) keys.add(`append.${a.field}`)
    }
    return keys
  })
  function isHeaderFilterable(f: SchemaField) {
    if (ftypeOf(f) === 'UPLOADS') return false
    if (!isDigestMode.value) return true
    const key = f.uukey || f.index || ''
    return !digestMetricKeys.value.has(key)
  }

  function clickCtype(c: SchemaClick): 'button' | 'action' {
    return String(c.ctype || 'button').toLowerCase() === 'action' ? 'action' : 'button'
  }

  const buttonClicks = computed(() =>
    (props.table.clicks || []).filter((c) => clickCtype(c) === 'button'),
  )
  const actionClicks = computed(() =>
    (props.table.clicks || []).filter((c) => clickCtype(c) === 'action'),
  )

  const toolbarClusters = computed(() => {
    const out: { key: string; group?: string; clicks: SchemaClick[] }[] = []
    for (const c of buttonClicks.value) {
      const g = String(c.group || '').trim() || undefined
      const last = out[out.length - 1]
      if (g && last?.group === g) {
        last.clicks.push(c)
        continue
      }
      out.push({ key: g ? `g:${g}` : c.uukey, group: g, clicks: [c] })
    }
    return out
  })

  const stickyKeys = computed(() => {
    const sticky = props.table.sticky
    const keys = sticky?.length ? [...sticky] : ['basic.uukey']
    return keys.filter((k) => fields.value.some((f) => f.uukey === k || `basic.${f.field}` === k))
  })

  function fieldId(f: SchemaField) {
    return f.uukey || fieldKey(f)
  }

  function columnLabel(f: SchemaField) {
    return String(f.label || f.field || fieldId(f))
  }

  /** 本视图可配置的列。未保存过时：默认显示的列按 sticky 靠前，schema 隐藏列排在后面 */
  const columnItems = computed(() => {
    const all = fields.value.filter((f) => f.field)
    const byId = new Map(all.map((f) => [fieldId(f), f]))
    const saved = columnOrder.value
    let keys: string[]
    if (saved && saved.length) {
      keys = saved.filter((k) => byId.has(k))
      for (const f of all) {
        const id = fieldId(f)
        if (!keys.includes(id)) keys.push(id)
      }
    } else {
      const shown = all.filter((f) => f.shown !== false).map(fieldId)
      const rest = all.filter((f) => f.shown === false).map(fieldId)
      keys = [...applyStickyOrder(shown, stickyKeys.value), ...rest]
    }
    const hidden = new Set(
      columnHidden.value ?? all.filter((f) => f.shown === false).map(fieldId),
    )
    return keys.map((id) => {
      const f = byId.get(id)!
      return {
        id,
        label: columnLabel(f),
        visible: !hidden.has(id),
      }
    })
  })

  const displayFields = computed(() => {
    const byId = new Map(fields.value.filter((f) => f.field).map((f) => [fieldId(f), f]))
    return columnItems.value
      .filter((item) => item.visible)
      .map((item) => byId.get(item.id))
      .filter((f): f is SchemaField => !!f)
  })

  const visibleColumnCount = computed(() => columnItems.value.filter((item) => item.visible).length)
  const columnsCustomized = computed(() => columnOrder.value !== null || columnHidden.value !== null)

  const pages = computed(() => Math.max(1, Math.ceil(count.value / size.value)))

  function fieldWidth(f: SchemaField) {
    const id = fieldKey(f) || f.field
    if (id && colWidths[id]) return colWidths[id]
    if (f.field && colWidths[f.field]) return colWidths[f.field]
    return Math.max(80, Number(f.width) || 140)
  }

  function applyWidthMap(map: Record<string, number>) {
    for (const [k, n] of Object.entries(map)) {
      if (!Number.isFinite(n)) continue
      if (k === ACTION_KEY) {
        if (n >= actionResizeMin.value) actionWidth.value = n
        continue
      }
      if (n >= 60) colWidths[k] = n
    }
  }

  function applyColumnLayout(layout: { order: string[]; hidden: string[] } | null) {
    if (!layout) {
      columnOrder.value = null
      columnHidden.value = null
      return
    }
    columnOrder.value = layout.order
    columnHidden.value = layout.hidden
  }

  async function loadWidths() {
    for (const k of Object.keys(colWidths)) delete colWidths[k]
    actionWidth.value = actionResizeMin.value
    columnOrder.value = null
    columnHidden.value = null
    const model = props.table.model
    const view = using.value
    const mod = modFromModel(model)
    if (!mod) return
    try {
      const [layout, columns] = await Promise.all([
        gateway.fetchTableLayout(mod),
        gateway.fetchTableColumns(model, view),
      ])
      if (props.table.model !== model || using.value !== view) return
      applyWidthMap(viewWidths(layout, model, view))
      applyColumnLayout(columns)
    } catch {
      /* ignore */
    }
  }

  function saveColumnPrefs() {
    gateway.saveTableColumns(props.table.model, using.value, {
      order: columnOrder.value || [],
      hidden: columnHidden.value || [],
    })
  }

  function toggleColumn(id: string) {
    const key = String(id || '').trim()
    if (!key) return
    const items = columnItems.value
    const hidden = new Set(
      columnHidden.value ?? items.filter((item) => !item.visible).map((item) => item.id),
    )
    if (hidden.has(key)) hidden.delete(key)
    else if (items.filter((item) => item.visible).length <= 1) return
    else hidden.add(key)
    if (!columnOrder.value?.length) columnOrder.value = items.map((item) => item.id)
    columnHidden.value = [...hidden]
    saveColumnPrefs()
  }

  function moveColumn(from: number, to: number) {
    const items = columnItems.value
    if (from < 0 || to < 0 || from >= items.length || to >= items.length || from === to) return
    const order = items.map((item) => item.id)
    const [row] = order.splice(from, 1)
    order.splice(to, 0, row)
    if (!columnHidden.value) {
      columnHidden.value = items.filter((item) => !item.visible).map((item) => item.id)
    }
    columnOrder.value = order
    saveColumnPrefs()
  }

  function resetColumns() {
    columnOrder.value = null
    columnHidden.value = null
    gateway.saveTableColumns(props.table.model, using.value, null)
  }

  function closeColumns() {
    columnOpen.value = false
  }

  function toggleColumns() {
    columnOpen.value = !columnOpen.value
    if (columnOpen.value) panelFilterOpen.value = false
  }

  function persistWidth(id: string, w: number) {
    gateway.patchTableWidth(props.table.model, using.value, id, w)
  }

  function keyIsSticky(f: SchemaField) {
    return stickyKeys.value.includes(f.uukey) || stickyKeys.value.includes(`basic.${f.field}`)
  }

  /** 只有从左侧连续排在最前的固定列才冻结，避免用户把普通列插到前面后错位 */
  function isStickyField(f: SchemaField) {
    const id = fieldId(f)
    for (const sf of displayFields.value) {
      if (!keyIsSticky(sf)) return false
      if (fieldId(sf) === id) return true
    }
    return false
  }

  function stickyLeft(f: SchemaField) {
    // 无操作按钮时不预留操作列宽度，否则 sticky 字段 left 会空出一截
    let left = CHECK_W + (actionClicks.value.length > 0 ? actionWidth.value : 0)
    for (const sf of displayFields.value) {
      if ((fieldKey(sf) || sf.field) === (fieldKey(f) || f.field)) break
      if (!isStickyField(sf)) break
      left += fieldWidth(sf)
    }
    return left
  }

  function isLastStickyField(f: SchemaField) {
    const stickyFs = displayFields.value.filter(isStickyField)
    return stickyFs.length > 0 && stickyFs[stickyFs.length - 1]?.field === f.field
  }

  function stickyEdgeOnAction() {
    return displayFields.value.filter(isStickyField).length === 0
  }

  function stickyEdgeOnCheck() {
    // 无操作列且无 sticky 字段时，勾选列是最后一列 sticky
    return (
      actionClicks.value.length === 0 &&
      displayFields.value.filter(isStickyField).length === 0
    )
  }

  function startResize(e: MouseEvent, id: string, current: number, min = 60) {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startW = current
    const prevCursor = document.body.style.cursor
    const prevSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(min, startW + (ev.clientX - startX))
      if (id === ACTION_KEY) actionWidth.value = w
      else colWidths[id] = w
    }
    const onUp = () => {
      const w = id === ACTION_KEY ? actionWidth.value : colWidths[id] || startW
      persistWidth(id, w)
      document.body.style.cursor = prevCursor
      document.body.style.userSelect = prevSelect
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  function rowKey(row: Record<string, unknown>) {
    return rowUUKey(row)
  }

  const allSelected = computed(
    () =>
      rows.value.length > 0 &&
      rows.value.every((r) => {
        const k = rowKey(r)
        return !!k && selectedKeys.value.includes(k)
      }),
  )
  const someSelected = computed(() => selectedKeys.value.length > 0 && !allSelected.value)

  function isRowSelected(row: Record<string, unknown>) {
    const key = rowKey(row)
    return !!key && selectedKeys.value.includes(key)
  }

  function displayCell(row: Record<string, unknown>, f: SchemaField) {
    return displayFieldValue(row, f, { refers: theRefers.value })
  }

  function totalValue(f: SchemaField): unknown {
    const t = totals.value || {}
    if (f.uukey in t) return t[f.uukey]
    if (f.field && f.field in t) return t[f.field]
    return undefined
  }

  function isNumericCol(f: SchemaField) {
    return isNumericField(f)
  }

  function formatTotalCell(f: SchemaField): string {
    const raw = totalValue(f)
    if (raw == null || raw === '') return ''
    const n = Number(raw)
    if (!Number.isFinite(n)) return String(raw)
    // RELATION unique / 行数：整数
    if (!isNumericCol(f) || ftypeOf(f) === 'RELATION') {
      return new Intl.NumberFormat('zh-CN', { useGrouping: false, maximumFractionDigits: 0 }).format(
        n,
      )
    }
    return formatNumericDisplay(raw, f)
  }

  const hasTotals = computed(() =>
    displayFields.value.some((f) => {
      const v = totalValue(f)
      return v != null && v !== ''
    }),
  )

  function optionsOf(f: SchemaField) {
    return referOptions(f, theRefers.value)
  }
  function hasReferOptions(f: SchemaField) {
    return optionsOf(f).length > 0
  }
  /** facet unique → 下拉；RELATION/OPTIONAL 用 refers 把 value 译成展示文案 */
  function facetOptions(f: SchemaField): { value: string; label: string }[] | null {
    const fk = fieldKey(f)
    const hit = facets.value[fk] || facets.value[f.uukey]
    if (!hit || hit.overflow) return null
    const opts = hit.options || []
    if (!opts.length || opts.length > 100) return null
    const ft = ftypeOf(f)
    if (ft === 'RELATION' || ft === 'OPTIONAL') {
      return opts.map((o) => {
        const value = String(o.value ?? '')
        const labeled = convertReferValue(f, value, theRefers.value)
        return { value, label: labeled || String(o.label || value) }
      })
    }
    return opts.map((o) => ({
      value: String(o.value ?? ''),
      label: String(o.label || o.value || ''),
    }))
  }
  function useFacetFilter(f: SchemaField) {
    // 日期字段走区间，不用 unique 下拉（会变成 IN，对 datetime 不准）
    if (ftypeOf(f) === 'DATETIME') return false
    return !!facetOptions(f)
  }
  /** 快捷/表头下拉：优先 facet unique（已译 label），否则 refers */
  function selectOptionsOf(f: SchemaField) {
    return facetOptions(f) || optionsOf(f)
  }
  function ftypeOf(f: SchemaField) {
    return String(f.ftype || '').toUpperCase()
  }

  type QuickFilterKind = 'select' | 'relation' | 'daterange' | 'text'
  type QuickFilterGroup = { field: SchemaField; kind: QuickFilterKind }

  function findFieldByKey(key: string): SchemaField | undefined {
    return fieldForFilter(String(key))
  }

  const quickFilterGroups = computed((): QuickFilterGroup[] => {
    const keys = props.table.filters || []
    if (!keys.length) return []
    const out: QuickFilterGroup[] = []
    for (const key of keys) {
      const f = findFieldByKey(String(key))
      if (!f || !isHeaderFilterable(f)) continue
      const ft = ftypeOf(f)
      // 日期始终区间筛选，不走 facet 下拉（避免 IN 精确匹配时间戳失败）
      if (ft === 'DATETIME') {
        out.push({ field: f, kind: 'daterange' })
        continue
      }
      // 财务期间等数值账期：快捷文本（可输 202608）
      if (
        (ft === 'NUMERIC' || ft === 'INTEGER') &&
        (String(f.field || '').toLowerCase() === 'uterm' || fieldKey(f).endsWith('.uterm'))
      ) {
        out.push({ field: f, kind: 'text' })
        continue
      }
      // RELATION，以及多选 OPTIONAL（标签）：可搜索多选，查询用包含任一
      if (ft === 'RELATION' || (ft === 'OPTIONAL' && isMultiple(f))) {
        if (!selectOptionsOf(f).length) continue
        out.push({ field: f, kind: 'relation' })
        continue
      }
      // unique≤100：快捷筛选也用下拉（可搜索）
      if (facetOptions(f)) {
        out.push({ field: f, kind: 'select' })
        continue
      }
      if (ft === 'OPTIONAL' || hasReferOptions(f)) {
        if (!optionsOf(f).length) continue
        out.push({ field: f, kind: 'select' })
        continue
      }
      if (
        ft === 'STRINGS' ||
        ft === 'SUBJECT' ||
        ft === 'KEYWORDS' ||
        ft === 'SERIALNO' ||
        ft === 'LONGTEXT'
      ) {
        out.push({ field: f, kind: 'text' })
      }
    }
    return out
  })

  function quickSelectValue(f: SchemaField): string {
    const cur = appliedFilters[fieldKey(f)]
    if (!cur || !isDraftActive(cur) || cur.op !== 'EQ') return ''
    return String(cur.value ?? '')
  }

  /** 写入 applied；列头 draft 仅在打开时从 applied 同步，避免三处双写 */
  function setApplied(fk: string, draft: FilterDraft | null) {
    if (!draft || !isDraftActive(draft)) {
      delete appliedFilters[fk]
      delete filterDraft[fk]
    } else {
      appliedFilters[fk] = { op: draft.op, value: draft.value, value2: draft.value2 }
      if (filterDraft[fk]) {
        filterDraft[fk] = { op: draft.op, value: draft.value, value2: draft.value2 }
      }
    }
    page.value = 1
    void reload()
  }

  function setQuickSelect(f: SchemaField, value: string | string[]) {
    const fk = fieldKey(f)
    const v = Array.isArray(value) ? String(value[0] || '').trim() : String(value ?? '').trim()
    setApplied(fk, v ? { op: 'EQ', value: v, value2: '' } : null)
  }

  function quickRelationValue(f: SchemaField): string[] {
    const cur = appliedFilters[fieldKey(f)]
    if (!cur || !isDraftActive(cur)) return []
    if (cur.op === 'IN') {
      return String(cur.value ?? '')
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean)
    }
    if (cur.op === 'EQ' && String(cur.value ?? '').trim()) {
      return [String(cur.value).trim()]
    }
    return []
  }

  function setQuickRelation(f: SchemaField, value: string | string[]) {
    const fk = fieldKey(f)
    const vals = (Array.isArray(value) ? value : [value])
      .map((v) => String(v ?? '').trim())
      .filter(Boolean)
    setApplied(fk, vals.length ? { op: 'IN', value: vals.join(','), value2: '' } : null)
  }

  function quickTextValue(f: SchemaField): string {
    const cur = appliedFilters[fieldKey(f)]
    if (!cur || !isDraftActive(cur)) return ''
    if (cur.op === 'LIKE' || cur.op === 'EQ' || cur.op === 'IN') return String(cur.value ?? '')
    return ''
  }

  function setQuickText(f: SchemaField, value: string) {
    const fk = fieldKey(f)
    const v = String(value ?? '').trim()
    if (!v) {
      setApplied(fk, null)
      return
    }
    const isUterm =
      String(f.field || '').toLowerCase() === 'uterm' || fieldKey(f).endsWith('.uterm')
    setApplied(fk, { op: isUterm ? 'EQ' : 'LIKE', value: v, value2: '' })
  }

  function quickRangeStart(f: SchemaField): string {
    return dateRangeFromDraft(appliedFilters[fieldKey(f)]).start
  }

  function quickRangeEnd(f: SchemaField): string {
    return dateRangeFromDraft(appliedFilters[fieldKey(f)]).end
  }

  function setQuickRange(f: SchemaField, start: string, end: string) {
    setApplied(fieldKey(f), draftFromDateRange(start, end))
  }

  function buildQuery(): Record<string, unknown> | undefined {
    const byKey = new Map<string, SchemaField>()
    for (const f of fields.value) {
      const k = fieldKey(f)
      byKey.set(k, originMap.value[k] || f)
    }
    for (const [k, f] of Object.entries(originMap.value)) {
      if (!byKey.has(k)) byKey.set(k, f)
    }
    return mergeListQuery(buildListQuery(appliedFilters, [...byKey.values()]), baseQuery)
  }

  function seedQueryDefaults() {
    for (const k of Object.keys(baseQuery)) delete baseQuery[k]
    const raw = { ...(props.table.request?.query || {}) }
    for (const [k, v] of Object.entries(raw)) {
      if (k.endsWith(':RCT')) {
        const fk = k.slice(0, -4)
        const { start, end } = expandRctToken(String(v ?? ''))
        const draft = draftFromDateRange(start, end)
        if (draft) {
          appliedFilters[fk] = draft
          filterDraft[fk] = { ...draft }
        }
        continue
      }
      baseQuery[k] = v
    }
  }

  function emitRequestChange() {
    options?.onRequestChange?.({
      page: page.value,
      size: size.value,
      query: buildQuery(),
    })
  }

  function getListRequest() {
    return {
      page: page.value,
      size: size.value,
      query: buildQuery(),
      // 聚合表排序前端本地完成，不传 order
      order: isDigestMode.value ? undefined : order.value || undefined,
    }
  }

  function compareSortVal(a: unknown, b: unknown, numeric: boolean): number {
    const aEmpty = a == null || a === ''
    const bEmpty = b == null || b === ''
    if (aEmpty && bEmpty) return 0
    if (aEmpty) return 1
    if (bEmpty) return -1
    if (numeric) {
      const na = Number(a)
      const nb = Number(b)
      if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb
    }
    return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
  }

  /** 聚合模式：对当前页结果本地排序；普通模式：rows 原样 */
  const displayRows = computed(() => {
    const list = rows.value
    if (!isDigestMode.value || !order.value) return list
    const key = order.value.field
    const f = fields.value.find((x) => (x.uukey || x.index) === key)
    if (!f) return list
    const numeric = isNumericField(f)
    const dir = order.value.order === 'desc' ? -1 : 1
    return [...list].sort((ra, rb) => compareSortVal(pickFieldValue(ra, f), pickFieldValue(rb, f), numeric) * dir)
  })

  async function reload() {
    emitRequestChange()
    if (props.hideBody) {
      rows.value = []
      totals.value = {}
      facets.value = {}
      count.value = 0
      selectedKeys.value = []
      loading.value = false
      return
    }
    loading.value = true
    error.value = ''
    try {
      const res = await gateway.searchRecords(props.table.model, using.value, page.value, size.value, {
        query: buildQuery(),
        order: isDigestMode.value ? undefined : order.value || undefined,
      })
      rows.value = res.values || []
      totals.value = (res.totals || {}) as Record<string, unknown>
      facets.value = (res.facets || {}) as Record<string, SearchFacet>
      count.value = res.count ?? rows.value.length
      theRefers.value = mergeRefers(
        normalizeReferDict(props.table.refers as ReferDict),
        normalizeReferDict(res.refers),
      )
      selectedKeys.value = []
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      totals.value = {}
      facets.value = {}
      count.value = 0
    } finally {
      loading.value = false
    }
  }

  function goto(p: number) {
    page.value = Math.min(Math.max(1, p), pages.value)
    void reload()
  }

  function setPageSize(n: number) {
    const next = PAGE_SIZES.includes(n as (typeof PAGE_SIZES)[number]) ? n : 100
    if (size.value === next) return
    size.value = next
    page.value = 1
    void reload()
  }

  function toggleSort(f: SchemaField) {
    if (!isSortableField(f)) return
    const field = sortIndexField(f)
    if (!order.value || order.value.field !== field) {
      order.value = { field, order: 'asc' }
    } else if (order.value.order === 'asc') {
      order.value = { field, order: 'desc' }
    } else {
      order.value = null
    }
    if (isDigestMode.value) {
      emitRequestChange()
      return
    }
    page.value = 1
    void reload()
  }

  function sortState(f: SchemaField): 'asc' | 'desc' | '' {
    const field = sortIndexField(f)
    if (!isSortableField(f) || !order.value || order.value.field !== field) return ''
    return order.value.order === 'desc' ? 'desc' : 'asc'
  }

  function ensureDraft(f: SchemaField) {
    const fk = fieldKey(f)
    if (!filterDraft[fk]) {
      const applied = appliedFilters[fk]
      filterDraft[fk] = {
        op: applied?.op || defaultOp(f),
        value: applied?.value || '',
        value2: applied?.value2 || '',
      }
    }
    return filterDraft[fk]
  }

  function openFilter(f: SchemaField) {
    const fk = fieldKey(f)
    const applied = appliedFilters[fk]
    filterDraft[fk] = {
      op: applied?.op || defaultOp(f),
      value: applied?.value || '',
      value2: applied?.value2 || '',
    }
    filterOpen.value = filterOpen.value === fk ? null : fk
  }

  function closeFilter() {
    filterOpen.value = null
  }

  function hasFilter(f: SchemaField) {
    return isDraftActive(appliedFilters[fieldKey(f)])
  }

  function multiFilterValue(f: SchemaField): string[] {
    const v = ensureDraft(f).value
    return String(v ?? '')
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
  }

  function onMultiFilterValue(f: SchemaField, v: string | string[]) {
    const arr = (Array.isArray(v) ? v : [v]).map((s) => String(s).trim()).filter(Boolean)
    const d = ensureDraft(f)
    d.value = arr.join('\n')
    if (arr.length) d.op = 'IN'
    else if (d.op === 'IN') d.op = 'ALL'
  }

  function applyFilter(f: SchemaField) {
    const d = ensureDraft(f)
    if (needsValue2(d.op) && (!d.value || !d.value2)) {
      error.value = t('widget.fillRange')
      return
    }
    if (d.op === 'ALL' && String(d.value ?? '').trim()) {
      d.op = hasReferOptions(f) ? 'IN' : 'LIKE'
    }
    const fk = fieldKey(f)
    if (!isDraftActive(d)) {
      delete appliedFilters[fk]
    } else {
      appliedFilters[fk] = { op: d.op, value: d.value, value2: d.value2 }
    }
    filterOpen.value = null
    page.value = 1
    void reload()
  }

  function clearFilter(f: SchemaField) {
    const fk = fieldKey(f)
    delete appliedFilters[fk]
    filterDraft[fk] = { op: defaultOp(f), value: '', value2: '' }
    filterOpen.value = null
    page.value = 1
    void reload()
  }

  function clearAllFilters() {
    for (const k of Object.keys(appliedFilters)) delete appliedFilters[k]
    for (const k of Object.keys(filterDraft)) delete filterDraft[k]
    filterOpen.value = null
    page.value = 1
    void reload()
  }

  function onPanelFilters(next: Record<string, FilterDraft>) {
    for (const k of Object.keys(appliedFilters)) delete appliedFilters[k]
    for (const k of Object.keys(filterDraft)) delete filterDraft[k]
    for (const [k, v] of Object.entries(next || {})) {
      if (!v || !isDraftActive(v)) continue
      appliedFilters[k] = { op: v.op, value: v.value, value2: v.value2 }
    }
    page.value = 1
    void reload()
  }

  function closePanelFilter() {
    panelFilterOpen.value = false
  }

  function togglePanelFilter() {
    panelFilterOpen.value = !panelFilterOpen.value
    if (panelFilterOpen.value) columnOpen.value = false
  }

  const activeFilterCount = computed(
    () => Object.values(appliedFilters).filter((d) => isDraftActive(d)).length,
  )

  function toggleAll(e?: Event) {
    const el = e?.target as HTMLInputElement | undefined
    const checked = el && typeof el.checked === 'boolean' ? el.checked : !allSelected.value
    selectedKeys.value = checked ? rows.value.map(rowKey).filter((k) => !!k) : []
  }

  function toggleOne(key: string, e?: Event) {
    const k = String(key || '').trim()
    if (!k) return
    const el = e?.target as HTMLInputElement | undefined
    const checked =
      el && typeof el.checked === 'boolean' ? el.checked : !selectedKeys.value.includes(k)
    if (checked) {
      if (!selectedKeys.value.includes(k)) selectedKeys.value = [...selectedKeys.value, k]
    } else {
      selectedKeys.value = selectedKeys.value.filter((x) => x !== k)
    }
  }

  function getSelectedRows() {
    const set = new Set(selectedKeys.value)
    // 聚合表按当前展示顺序（含前端排序）导出选中
    const source = isDigestMode.value ? displayRows.value : rows.value
    return source.filter((r) => set.has(rowKey(r)))
  }

  async function deleteSelected() {
    const keys = [...selectedKeys.value].map(String).filter((k) => k.trim())
    if (!keys.length) {
      error.value = t('widget.pickDeleteRows')
      return
    }
    if (!confirm(t('widget.confirmDeleteRows', { n: keys.length }))) return
    error.value = ''
    try {
      await gateway.deleteRecords(props.table.model, keys)
      selectedKeys.value = []
      await reload()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function exportByQuery() {
    try {
      const pageSize = 100
      const max = 500
      const all: Record<string, unknown>[] = []
      let pageNo = 1
      let total = Infinity
      const q = buildQuery()
      while (all.length < max && all.length < total) {
        const res = await gateway.searchRecords(props.table.model, using.value, pageNo, pageSize, {
          query: q,
          order: isDigestMode.value ? undefined : order.value || undefined,
        })
        total = res.count ?? 0
        const batch = res.values || []
        if (!batch.length) break
        all.push(...batch)
        Object.assign(theRefers.value, normalizeReferDict(res.refers))
        if (batch.length < pageSize) break
        pageNo += 1
      }
      if (!all.length) {
        error.value = t('widget.noExportData')
        return
      }
      if (total > max && !confirm(t('widget.exportTruncated', { total, max }))) return
      await exportRows({
        title: props.table.title?.trim() || props.table.model,
        fields: displayFields.value,
        rows: all.slice(0, max),
        refers: theRefers.value,
      })
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function exportSelected() {
    const selected = getSelectedRows()
    if (!selected.length) {
      error.value = t('widget.pickExportRows')
      return
    }
    try {
      await exportRows({
        title: props.table.title?.trim() || props.table.model,
        fields: displayFields.value,
        rows: selected,
        refers: theRefers.value,
      })
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function onDocClick(ev: MouseEvent) {
    if (!filterOpen.value) return
    const t = ev.target as HTMLElement | null
    if (
      t?.closest?.('.filter-pop') ||
      t?.closest?.('.hdr-icon') ||
      t?.closest?.('.select-panel') ||
      t?.closest?.('.dropdown-panel')
    ) {
      return
    }
    filterOpen.value = null
  }

  watch(actionResizeMin, (min) => {
    if (actionWidth.value < min) actionWidth.value = min
  })

  watch(
    () => props.table.model,
    () => {
      page.value = 1
      order.value = null
      columnOpen.value = false
      panelFilterOpen.value = false
      for (const k of Object.keys(appliedFilters)) delete appliedFilters[k]
      for (const k of Object.keys(filterDraft)) delete filterDraft[k]
      seedQueryDefaults()
      loadWidths()
      void reload()
    },
  )

  watch(using, (next, prev) => {
    if (next === prev) return
    columnOpen.value = false
    panelFilterOpen.value = false
    loadWidths()
  })

  watch(
    () => props.hideBody,
    (hide, prev) => {
      if (hide === prev) return
      if (!hide) void reload()
      else emitRequestChange()
    },
  )

  onMounted(() => {
    loadWidths()
    theRefers.value = normalizeReferDict(props.table.refers as ReferDict)
    const req = props.table.request
    if (req?.page) page.value = req.page
    if (req?.size != null) {
      const n = Number(req.size)
      size.value = PAGE_SIZES.includes(n as (typeof PAGE_SIZES)[number]) ? n : 100
    }    if (req?.order?.field) {
      order.value = {
        field: req.order.field,
        order: req.order.order === 'asc' ? 'asc' : 'desc',
      }
    }
    seedQueryDefaults()
    document.addEventListener('click', onDocClick)
    void reload()
  })

  onUnmounted(() => {
    document.removeEventListener('click', onDocClick)
  })

  return reactive({
    /** 布局 / 列宽 / sticky */
    layout: {
      CHECK_W,
      ACTION_MIN,
      ACTION_KEY,
      actionResizeMin,
      actionWidth,
      displayFields,
      fieldKey,
      fieldWidth,
      stickyLeft,
      startResize,
      isNumericCol,
      isStickyField,
      isLastStickyField,
      stickyEdgeOnAction,
      stickyEdgeOnCheck,
    },
    /** 列表数据与分页 */
    list: {
      rows,
      displayRows,
      totals,
      count,
      page,
      size,
      pages,
      pageSizes: PAGE_SIZES,
      error,
      loading,
      fields,
      using,
      theRefers,
      hasTotals,
      goto,
      setPageSize,
      reload,
      getListRequest,
      emitRequestChange,
    },
    /** 工具栏 clicks */
    toolbar: {
      toolbarClusters,
      actionClicks,
    },
    /** 行选择 */
    selection: {
      selectedKeys,
      allSelected,
      someSelected,
      toggleAll,
      toggleOne,
      getSelectedRows,
      getSelectedKeys: () => [...selectedKeys.value],
      rowKey,
      isRowSelected,
    },
    /** 单元格展示 */
    cell: {
      displayCell,
      formatTotalCell,
    },
    /** 排序 */
    sort: {
      sortState,
      toggleSort,
      isSortableField,
      isHeaderFilterable,
    },
    /** 表头/快捷/面板筛选 */
    filter: {
      filterOpen,
      panelFilterOpen,
      appliedFilters,
      activeFilterCount,
      optionsOf,
      hasReferOptions,
      facetOptions,
      useFacetFilter,
      selectOptionsOf,
      ftypeOf,
      filterOps,
      showValue,
      needsValue2,
      ensureDraft,
      openFilter,
      closeFilter,
      hasFilter,
      multiFilterValue,
      onMultiFilterValue,
      applyFilter,
      clearFilter,
      clearAllFilters,
      onPanelFilters,
      togglePanelFilter,
      closePanelFilter,
      panelFilterFields,
      fieldForFilter,
      quickFilterGroups,
      quickSelectValue,
      setQuickSelect,
      quickRelationValue,
      setQuickRelation,
      quickTextValue,
      setQuickText,
      quickRangeStart,
      quickRangeEnd,
      setQuickRange,
    },
    /** 列显隐与顺序 */
    columns: {
      open: columnOpen,
      items: columnItems,
      visibleCount: visibleColumnCount,
      customized: columnsCustomized,
      toggleOpen: toggleColumns,
      close: closeColumns,
      toggle: toggleColumn,
      move: moveColumn,
      reset: resetColumns,
    },
    /** 批量操作 */
    actions: {
      exportByQuery,
      exportSelected,
      deleteSelected,
    },
  })
}
