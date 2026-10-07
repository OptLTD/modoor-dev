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
  normalizeReferDict,
  resolveModelTitle,
  searchRecords,
  type ReferDict,
  type SchemaField,
} from '@modoor/hooks'
import { ChartGrid, type ChartGridCard } from '@modoor/widget/ChartGrid'
import RecordDrawer from '../RecordDrawer/RecordDrawer.vue'
import RecordFlatDetail from '../RecordDrawer/RecordFlatDetail.vue'
import { resolveRecordView } from '../RecordDrawer/recordViews'
import TableDrawer from '../TableDrawer/TableDrawer.vue'
import { chartSlotStyle } from './layout'
import { chartSearchQuery } from './query'
import type { ChartBoard, ChartCard, ChartsFile } from './types'

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
    const refers: ReferDict = normalizeReferDict({
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

function loadCard(key: string, card: ChartCard) {
  if (card.type === 'count') void loadCount(key, card)
  else if (card.type === 'table') void loadTable(key, card)
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

const listOpen = ref(false)
const listCard = ref<ChartCard | null>(null)
const listTotal = ref<number | null>(null)

function openCount(key: string) {
  const card = cardAt(key)
  if (!card?.query?.model || counts.value[key]?.loading) return
  listCard.value = card
  listTotal.value = counts.value[key]?.total ?? null
  listOpen.value = true
}

const listModel = computed(() => String(listCard.value?.query?.model || ''))
const listUsing = computed(() => listCard.value?.query?.using || 'default')
const listQuery = computed(() => (listCard.value ? chartSearchQuery(listCard.value) : {}))
const listTitle = computed(() => {
  const card = listCard.value
  if (!card) return ''
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
  />

  <TableDrawer
    :open="listOpen"
    :title="listTitle"
    :model="listModel"
    :using="listUsing"
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
