<script setup lang="ts">
/**
 * 看板页：解析页签和格子位置，拉取指标/表格，再交给 ChartGrid 渲染。
 * count 下钻走 TableDrawer，表格行打开 RecordDrawer。
 */
import { computed, ref, watch } from 'vue'
import {
  displayFieldValue,
  entityLabel,
  fetchSchema,
  normalizeRefer,
  resolveModelTitle,
  get,
  searchRecords,
  type ReferDict,
  type SchemaField,
} from '@modoor/hooks'
import { ChartGrid, type ChartGridCard } from '@modoor/widget/ChartGrid'
import RecordDrawer from '../RecordDrawer/RecordDrawer.vue'
import RecordFlatDetail from '../RecordDrawer/RecordFlatDetail.vue'
import { resolveRecordView } from '../RecordDrawer/recordViews'
import TableDrawer from '../TableDrawer/TableDrawer.vue'
import {
  diffAmount,
  queryForTerm,
  reportUrl,
  scopeUterm,
  sumTotals,
  type DiffScope,
} from './diff'
import { chartSlotStyle } from './layout'
import { chartSearchQuery } from './query'
import type { ChartBoard, ChartCard, ChartValue, ChartsFile } from './types'

const props = withDefaults(
  defineProps<{
    title?: string
    charts: ChartsFile
    boards?: ChartBoard[]
    board?: string
  }>(),
  { title: '', boards: () => [], board: '' },
)

const emit = defineEmits<{
  'update:board': [id: string]
}>()

type CountState = { loading: boolean; error: string; total: number | null }
type DiffState = {
  loading: boolean
  error: string
  scope: DiffScope
  uterm: string
  left: number | null
  right: number | null
  total: number | null
  leftLabel: string
  rightLabel: string
  model: string
  using: string
  query: Record<string, unknown>
}
type TableState = {
  loading: boolean
  error: string
  columns: { key: string; label: string }[]
  rows: { key: string; uukey?: string; cells: string[] }[]
}

const resolvedBoards = computed<ChartBoard[]>(() => {
  if (props.boards.length) return props.boards
  return Object.keys(props.charts).map((id) => ({ id, label: id }))
})

const active = ref(
  props.board || resolvedBoards.value[0]?.id || Object.keys(props.charts)[0] || '',
)

watch(
  () => props.board,
  (id) => {
    if (id && id !== active.value) active.value = id
  },
)

const sourceCards = computed(() => (props.charts[active.value] || []) as ChartCard[])
const brief = computed(() => resolvedBoards.value.find((b) => b.id === active.value)?.brief || '')

function cardKey(card: ChartCard, index: number) {
  return `${active.value}-${card.title}-${index}`
}

const counts = ref<Record<string, CountState>>({})
const tables = ref<Record<string, TableState>>({})
const diffs = ref<Record<string, DiffState>>({})
const diffTickets = new Map<string, number>()

function setCount(key: string, patch: Partial<CountState>) {
  const prev: CountState = counts.value[key] || { loading: false, error: '', total: null }
  counts.value = { ...counts.value, [key]: { ...prev, ...patch } }
}

function setTable(key: string, patch: Partial<TableState>) {
  const prev = tables.value[key]
  tables.value = {
    ...tables.value,
    [key]: {
      loading: false,
      error: '',
      columns: prev?.columns || [],
      rows: prev?.rows || [],
      ...patch,
    },
  }
}

async function loadCount(key: string, card: ChartCard) {
  const model = String(card.query?.model || '')
  if (!model) return
  setCount(key, { loading: true, error: '' })
  try {
    const res = await searchRecords(model, card.query?.using || 'default', 1, 1, {
      query: chartSearchQuery(card),
    })
    setCount(key, { loading: false, total: Number(res.count || 0) })
  } catch (e) {
    setCount(key, {
      loading: false,
      error: e instanceof Error ? e.message : String(e),
      total: null,
    })
  }
}

async function loadTable(key: string, card: ChartCard) {
  const model = String(card.query?.model || '')
  if (!model) return
  setTable(key, { loading: true, error: '' })
  try {
    const using = card.query?.using || 'default'
    const schema = await fetchSchema(model, using)
    const all = schema.table.fields || []
    const keys = (card.option?.fields || []).map(String).filter(Boolean)
    const fields: SchemaField[] = keys.length
      ? keys.map((k) => all.find((f) => f.uukey === k)).filter((f): f is SchemaField => !!f)
      : all
    const res = await searchRecords(model, using, 1, card.query?.limit ?? 50, {
      query: chartSearchQuery(card),
    })
    const refers: ReferDict = normalizeRefer({
      ...((schema.table.refers || {}) as Record<string, unknown>),
      ...((res.refers || {}) as Record<string, unknown>),
    })
    const rows = ((res.values || []) as Record<string, unknown>[]).map((row, i) => ({
      key: String(row['basic.uukey'] || i),
      uukey: String(row['basic.uukey'] || '').trim(),
      cells: fields.map((field) => displayFieldValue(row, field, { refers }) || ''),
    }))
    setTable(key, {
      loading: false,
      columns: fields.map((field) => ({ key: field.uukey, label: field.label || field.uukey })),
      rows,
    })
  } catch (e) {
    setTable(key, {
      loading: false,
      error: e instanceof Error ? e.message : String(e),
      columns: [],
      rows: [],
    })
  }
}

function isDiffScope(value: string): value is DiffScope {
  return value === 'current' || value === 'previous' || value === 'earlier'
}

async function readValue(source: ChartValue, uterm: number): Promise<number> {
  if (source.type === 'report') {
    const body = await get<{ totals?: Record<string, unknown> }>(reportUrl(source, uterm))
    return sumTotals(body.totals, [String(source.total || '')])
  }
  const model = String(source.model || '')
  if (!model) throw new Error('缺少查询模型')
  const res = await searchRecords(model, source.using || 'default', 1, 1, {
    query: queryForTerm(source, uterm),
  })
  return sumTotals(res.totals, (source.sum || []).map(String))
}

function querySide(card: ChartCard): ChartValue | null {
  const q = card.query
  if (!q?.model) return null
  return {
    type: 'query',
    label: q.label,
    model: q.model,
    using: q.using,
    sum: q.sum,
    term: q.term,
    query: q.query,
  }
}

async function loadDiff(key: string, card: ChartCard, scope: DiffScope) {
  const left = querySide(card)
  const right = card.compare
  if (!left || !right) return
  const ticket = (diffTickets.get(key) || 0) + 1
  diffTickets.set(key, ticket)
  const prev = diffs.value[key]
  diffs.value = {
    ...diffs.value,
    [key]: {
      loading: true,
      error: '',
      scope,
      uterm: prev?.uterm || '',
      left: prev?.left ?? null,
      right: prev?.right ?? null,
      total: prev?.total ?? null,
      leftLabel: String(left.label || ''),
      rightLabel: String(right.label || ''),
      model: String(left.model || ''),
      using: left.using || 'default',
      query: prev?.query || {},
    },
  }
  try {
    const uterm = scopeUterm(scope)
    const [leftValue, rightValue] = await Promise.all([
      readValue(left, uterm),
      readValue(right, uterm),
    ])
    if (diffTickets.get(key) !== ticket) return
    diffs.value = {
      ...diffs.value,
      [key]: {
        loading: false,
        error: '',
        scope,
        uterm: String(uterm),
        left: leftValue,
        right: rightValue,
        total: diffAmount(leftValue, rightValue),
        leftLabel: String(left.label || ''),
        rightLabel: String(right.label || ''),
        model: String(left.model || ''),
        using: left.using || 'default',
        query: queryForTerm(left, uterm),
      },
    }
  } catch (e) {
    if (diffTickets.get(key) !== ticket) return
    diffs.value = {
      ...diffs.value,
      [key]: {
        ...(diffs.value[key] as DiffState),
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        total: null,
      },
    }
  }
}

function loadCard(key: string, card: ChartCard) {
  if (card.type === 'count') void loadCount(key, card)
  else if (card.type === 'table') void loadTable(key, card)
  else if (card.type === 'compare') void loadDiff(key, card, diffs.value[key]?.scope || 'current')
}

watch(
  sourceCards,
  (list) => {
    list.forEach((card, index) => loadCard(cardKey(card, index), card))
  },
  { immediate: true },
)

const cards = computed((): ChartGridCard[] =>
  sourceCards.value.map((card, index) => {
    const key = cardKey(card, index)
    const style = chartSlotStyle(card.layout)
    if (card.type === 'count') {
      const state = counts.value[key]
      return {
        key,
        title: card.title,
        type: card.type,
        style,
        loading: state?.loading,
        error: state?.error,
        total: state?.total ?? null,
        prefix: String(card.option?.prefix || ''),
        suffix: String(card.option?.suffix || ''),
        note: String(card.option?.note || ''),
        help: String(card.option?.help || ''),
        clickable: !!card.query?.model,
      }
    }
    if (card.type === 'table') {
      const state = tables.value[key]
      return {
        key,
        title: card.title,
        type: card.type,
        style,
        loading: state?.loading,
        error: state?.error,
        columns: state?.columns || [],
        rows: state?.rows || [],
      }
    }
    if (card.type === 'text') {
      return {
        key,
        title: card.title,
        type: card.type,
        style,
        content: String(card.option?.content || ''),
      }
    }
    if (card.type === 'compare') {
      const state = diffs.value[key]
      return {
        key,
        title: card.title,
        type: card.type,
        style,
        loading: state?.loading,
        error: state?.error,
        total: state?.total ?? null,
        suffix: String(card.option?.suffix || '元'),
        note: String(card.option?.note || ''),
        help: String(card.option?.help || ''),
        clickable: !!state?.model,
        scope: state?.scope || 'current',
        uterm: state?.uterm || '',
        left: state?.left ?? null,
        right: state?.right ?? null,
        leftLabel: state?.leftLabel || '',
        rightLabel: state?.rightLabel || '',
      }
    }
    return { key, title: card.title, type: card.type, style }
  }),
)

function selectBoard(id: string) {
  active.value = id
  emit('update:board', id)
}

function cardAt(key: string): ChartCard | undefined {
  return sourceCards.value.find((card, index) => cardKey(card, index) === key)
}

function refresh(key: string) {
  const card = cardAt(key)
  if (card) loadCard(key, card)
}

function onScope(payload: { key: string; scope: string }) {
  const card = cardAt(payload.key)
  if (!card || card.type !== 'compare' || !isDiffScope(payload.scope)) return
  if (diffs.value[payload.key]?.scope === payload.scope && !diffs.value[payload.key]?.error) return
  void loadDiff(payload.key, card, payload.scope)
}

const listOpen = ref(false)
const listCard = ref<ChartCard | null>(null)
const listTotal = ref<number | null>(null)
const listQueryOverride = ref<Record<string, unknown> | null>(null)
const listModelOverride = ref('')
const listUsingOverride = ref('')
const listUterm = ref('')

function openCount(key: string) {
  const card = cardAt(key)
  if (!card || counts.value[key]?.loading) return
  if (card.type === 'compare') {
    const state = diffs.value[key]
    if (!state?.model || state.loading) return
    listCard.value = card
    listTotal.value = null
    listQueryOverride.value = state.query
    listModelOverride.value = state.model
    listUsingOverride.value = state.using
    listUterm.value = state.uterm
    listOpen.value = true
    return
  }
  if (!card.query?.model) return
  listCard.value = card
  listTotal.value = counts.value[key]?.total ?? null
  listQueryOverride.value = null
  listModelOverride.value = ''
  listUsingOverride.value = ''
  listUterm.value = ''
  listOpen.value = true
}

const listModel = computed(
  () => listModelOverride.value || String(listCard.value?.query?.model || ''),
)
const listUsing = computed(() => listUsingOverride.value || listCard.value?.query?.using || 'default')
const listQuery = computed(() => {
  if (listQueryOverride.value) return listQueryOverride.value
  return listCard.value ? chartSearchQuery(listCard.value) : {}
})
const listFields = computed(() =>
  (listCard.value?.option?.fields || []).map((k) => String(k).trim()).filter(Boolean),
)
const listTitle = computed(() => {
  const card = listCard.value
  if (!card) return ''
  if (listUterm.value) return `${card.title} · ${listUterm.value} 期`
  return listTotal.value == null ? card.title : `${card.title} · ${listTotal.value}`
})

const drawerOpen = ref(false)
const drawerModel = ref('')
const drawerUukey = ref('')
const drawerTitle = ref('')
const drawerView = computed(() =>
  drawerOpen.value ? resolveRecordView(drawerModel.value) : undefined,
)

async function openRow(payload: { key: string; rowKey: string }) {
  const card = cardAt(payload.key)
  const model = String(card?.query?.model || '')
  const uk = payload.rowKey.trim()
  if (!card || !model || !uk) return
  drawerModel.value = model
  drawerUukey.value = uk
  drawerTitle.value = entityLabel(await resolveModelTitle(model), model)
  drawerOpen.value = true
}
</script>

<template>
  <ChartGrid
    :title="title"
    :tabs="resolvedBoards"
    :active="active"
    :brief="brief"
    :cards="cards"
    @update:active="selectBoard"
    @refresh="refresh"
    @open="openCount"
    @row="openRow"
    @scope="onScope"
  />

  <TableDrawer
    :open="listOpen"
    :title="listTitle"
    :model="listModel"
    :using="listUsing"
    :fields="listFields"
    :fixed-query="listQuery"
    @close="listOpen = false"
  />

  <RecordDrawer
    :open="drawerOpen"
    :title="drawerTitle"
    :wide="!!drawerView"
    :model="drawerModel"
    :uukey="drawerUukey"
    @close="drawerOpen = false"
  >
    <component
      :is="drawerView || RecordFlatDetail"
      :model="drawerModel"
      :uukey="drawerUukey || undefined"
      :lookup="{ 'basic.uukey': drawerUukey }"
      :title="drawerTitle"
      @close="drawerOpen = false"
    />
  </RecordDrawer>
</template>
