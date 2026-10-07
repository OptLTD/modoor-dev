<script setup lang="ts">
/**
 * 默认抽屉内容：DETAIL 字段平铺（上标签下值，按抽屉宽度 1–4 列）。
 */
import { computed, inject, ref, watch } from 'vue'
import {
  rowUUKey,
  useI18n,
  searchRecords,
  fetchInputSchema,
  formVisibleFields,
  normalizeReferDict,
  displayFieldValue,
  type SchemaField,
  type ReferDict,
} from '@modoor/hooks'
import RecordFields from './RecordFields.vue'
import { RECORD_DRAWER_OPLOG_KEY } from './oplogContext'

const props = defineProps<{
  model: string
  uukey?: string
  lookup?: Record<string, unknown>
}>()

const { t } = useI18n()
const oplogApi = inject(RECORD_DRAWER_OPLOG_KEY, null)
const loading = ref(false)
const error = ref('')
const fields = ref<SchemaField[]>([])
const values = ref<Record<string, unknown> | null>(null)
const refers = ref<ReferDict>({})

const visibleFields = computed(() => formVisibleFields(fields.value))

function displayOf(f: SchemaField) {
  return displayFieldValue(values.value || {}, f, { refers: refers.value })
}

/** 运单详情按业务类型选用同名 input：general / engineering。 */
function detailUsing(model: string, row: Record<string, unknown> | null): string {
  if (model !== 'capacity.waybill' || !row) return 'default'
  const kind = String(row['basic.biz_type'] ?? '')
  return kind === 'general' || kind === 'engineering' ? kind : 'default'
}

async function load() {
  if (!props.model) return
  loading.value = true
  error.value = ''
  fields.value = []
  values.value = null
  try {
    let uk = String(props.uukey || '').trim()
    if (!uk && props.lookup && Object.keys(props.lookup).length) {
      const res = await searchRecords(props.model, 'default', 1, 1, {
        query: props.lookup,
      })
      const row = (res.values || [])[0]
      if (!row) throw new Error(t('widget.recordNotFound') || '未找到关联记录')
      uk = rowUUKey(row)
      values.value = row
      refers.value = normalizeReferDict(res.refers)
    }
    if (!uk) throw new Error(t('widget.missingKey') || '缺少记录编号')
    oplogApi?.setTarget(props.model, uk)
    let using = detailUsing(props.model, values.value)
    let res = await fetchInputSchema(props.model, using, 'DETAIL', uk)
    fields.value = res.input?.fields || []
    if (res.input?.values) values.value = res.input.values as Record<string, unknown>
    refers.value = normalizeReferDict(res.input?.refers as ReferDict)
    const next = detailUsing(props.model, values.value)
    if (next !== using) {
      using = next
      res = await fetchInputSchema(props.model, using, 'DETAIL', uk)
      fields.value = res.input?.fields || []
      if (res.input?.values) values.value = res.input.values as Record<string, unknown>
      refers.value = normalizeReferDict(res.input?.refers as ReferDict)
    }
    if (!values.value) {
      const found = await searchRecords(props.model, 'default', 1, 1, {
        query: { 'basic.uukey': uk },
      })
      values.value = (found.values || [])[0] || { 'basic.uukey': uk }
      refers.value = normalizeReferDict(found.refers)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    oplogApi?.clearTarget()
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.model, props.uukey, JSON.stringify(props.lookup || {})] as const,
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="flat-detail">
    <p v-if="loading" class="muted">{{ t('widget.loading') }}</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <RecordFields v-else :fields="visibleFields" :display-of="displayOf" />
  </div>
</template>

<style scoped>
.flat-detail {
  padding: 12px 16px 24px;
}
.muted {
  color: var(--muted, #6b6458);
}
.error {
  color: #b42318;
}
</style>
