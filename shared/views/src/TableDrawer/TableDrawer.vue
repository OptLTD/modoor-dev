<script setup lang="ts">
/**
 * 右侧数据源抽屉：内嵌 SchemaTable，按 fixedQuery 过滤（报表下钻用）。
 * 单元格 SERIALNO / RELATION 点击打开嵌套 RecordDrawer。
 */
import { computed, ref, watch } from 'vue'
import {
  entityLabel,
  fetchSchema,
  resolveModelTitle,
  useI18n,
  type SchemaField,
  type SchemaTable,
} from '@modoor/hooks'
import SchemaTableView from '@modoor/widget/SchemaTable'
import RecordDrawer from '../RecordDrawer/RecordDrawer.vue'
import RecordFlatDetail from '../RecordDrawer/RecordFlatDetail.vue'
import { resolveRecordView } from '../RecordDrawer/recordViews'

const props = defineProps<{
  open: boolean
  title: string
  model: string
  fixedQuery?: Record<string, unknown>
  using?: string
}>()

const emit = defineEmits<{
  close: []
  'record-click': [
    payload: {
      model: string
      uukey?: string
      title?: string
      field?: SchemaField
      record?: Record<string, unknown>
      lookup?: Record<string, unknown>
    },
  ]
}>()

const { t } = useI18n()
const loading = ref(false)
const error = ref('')
const schema = ref<SchemaTable | null>(null)

const detailOpen = ref(false)
const detailModel = ref('')
const detailUukey = ref('')
const detailLookup = ref<Record<string, unknown> | undefined>()
const detailTitle = ref('')

const detailView = computed(() =>
  detailOpen.value ? resolveRecordView(detailModel.value) : undefined,
)

const table = computed((): SchemaTable | null => {
  if (!schema.value || !props.model) return null
  return {
    ...schema.value,
    model: props.model,
    using: props.using || schema.value.using || 'default',
    title: props.title || schema.value.title,
    clicks: [],
    request: {
      page: 1,
      size: 50,
      query: { ...(props.fixedQuery || {}) },
    },
  }
})

const remountKey = computed(
  () =>
    `${props.model}|${props.using || 'default'}|${JSON.stringify(props.fixedQuery || {})}`,
)

async function loadSchema() {
  if (!props.open || !props.model) return
  loading.value = true
  error.value = ''
  schema.value = null
  try {
    const res = await fetchSchema(props.model, props.using || 'default')
    schema.value = {
      ...res.table,
      model: res.model,
      using: res.using,
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function closeDetail() {
  detailOpen.value = false
  detailModel.value = ''
  detailUukey.value = ''
  detailLookup.value = undefined
  detailTitle.value = ''
}

async function onRecordClick(payload: {
  model: string
  uukey?: string
  title?: string
  field?: SchemaField
  record?: Record<string, unknown>
  lookup?: Record<string, unknown>
}) {
  emit('record-click', payload)
  detailModel.value = payload.model
  detailUukey.value = payload.uukey || ''
  detailLookup.value = payload.lookup
  const hint =
    payload.model === props.model ? props.title || schema.value?.title || '' : payload.title || ''
  detailTitle.value = entityLabel(await resolveModelTitle(payload.model, hint), payload.model)
  detailOpen.value = true
}

watch(
  () => [props.open, props.model, props.using, JSON.stringify(props.fixedQuery || {})] as const,
  ([open]) => {
    if (!open) closeDetail()
    if (open) void loadSchema()
  },
  { immediate: true },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="table-drawer-mask" @click.self="emit('close')">
      <aside class="table-drawer" role="dialog" aria-modal="true" :aria-label="title">
        <header class="td-head">
          <strong class="td-title truncate">{{ title }}</strong>
          <button type="button" class="link" @click="emit('close')">{{ t('widget.close') }}</button>
        </header>
        <div class="td-body">
          <p v-if="loading" class="muted pad">{{ t('widget.loading') }}</p>
          <p v-else-if="error" class="error pad">{{ error }}</p>
          <SchemaTableView
            v-else-if="table"
            :key="remountKey"
            class="td-table"
            :table="table"
            :using="table.using"
            @record-click="onRecordClick"
          />
        </div>
      </aside>
    </div>
  </Teleport>

  <RecordDrawer
    :open="detailOpen"
    :title="detailTitle"
    :wide="!!detailView"
    :model="detailModel"
    :uukey="detailUukey || undefined"
    elevated
    @close="closeDetail"
  >
    <component
      :is="detailView || RecordFlatDetail"
      :model="detailModel"
      :uukey="detailUukey || undefined"
      :lookup="detailLookup"
      :title="detailTitle"
      @close="closeDetail"
    />
  </RecordDrawer>
</template>

<style scoped>
.table-drawer-mask {
  inset: 0;
  position: fixed;
  z-index: 10080;
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, var(--ink, #1c1914) 28%, transparent);
}
.table-drawer {
  width: min(920px, 96vw);
  height: 100%;
  background: var(--panel, #fff);
  border-left: 1px solid var(--line, #e2e6eb);
  box-shadow: -8px 0 24px rgba(28, 25, 23, 0.12);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.td-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
}
.td-title {
  font-size: 0.95rem;
  min-width: 0;
}
.td-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* SchemaTable 根节点即 .table-wrap；页面靠 .workspace .table-wrap 拉高，抽屉需自行补齐 */
.td-table {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.td-table :deep(.toolbar) {
  flex-shrink: 0;
}
.td-table :deep(.table-body) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
.td-table :deep(.scroller) {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  overflow: auto;
}
.td-table :deep(.list-frame.has-totals) {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.td-table :deep(.list-spacer) {
  flex: 1 1 auto;
  min-height: 0;
}
.td-table :deep(.list-totals) {
  position: sticky;
  bottom: 0;
  z-index: 8;
  flex-shrink: 0;
}
.pad {
  padding: 16px;
}
.muted {
  color: var(--muted, #6b6458);
}
.error {
  color: #b42318;
}
.link {
  border: 0;
  background: transparent;
  color: var(--accent, #0f6a5a);
  cursor: pointer;
  font: inherit;
  padding: 0;
}
</style>
