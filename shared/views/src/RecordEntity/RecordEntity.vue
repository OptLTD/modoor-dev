<script setup lang="ts">
/**
 * 实体卡片：head + body(tabs) + foot(actions)。由模块作为 RecordDrawer 内容使用。
 */
import { computed, inject, ref, watch } from 'vue'
import {
  fetchInputSchema,
  fetchSchema,
  formVisibleFields,
  normalizeReferDict,
  displayFieldValue,
  rowUUKey,
  searchRecords,
  useI18n,
  type RecordEntityAction,
  type RecordEntityConfig,
  type RecordEntityTab,
  type SchemaField,
  type ReferDict,
} from '@modoor/hooks'
import RecordDialog from '../RecordDialog/RecordDialog.vue'
import RecordFields from '../RecordDrawer/RecordFields.vue'
import { RECORD_DRAWER_OPLOG_KEY } from '../RecordDrawer/oplogContext'

const props = defineProps<{
  model: string
  uukey?: string
  lookup?: Record<string, unknown>
  title?: string
  config: RecordEntityConfig
}>()

const emit = defineEmits<{
  close: []
  action: [payload: { id: string; action?: string; model: string; uukey: string }]
}>()

const { t } = useI18n()
const oplogApi = inject(RECORD_DRAWER_OPLOG_KEY, null)
const loading = ref(false)
const error = ref('')
const fields = ref<SchemaField[]>([])
const values = ref<Record<string, unknown> | null>(null)
const refers = ref<ReferDict>({})
const resolvedKey = ref('')
const activeTab = ref('')
const relatedLoading = ref(false)
const relatedError = ref('')
const relatedRows = ref<Record<string, unknown>[]>([])
const relatedFields = ref<SchemaField[]>([])
const relatedRefers = ref<ReferDict>({})
const formOpen = ref(false)
const formFields = ref<SchemaField[]>([])

const fieldByKey = computed(() => {
  const map = new Map<string, SchemaField>()
  for (const f of fields.value) map.set(f.uukey || f.index || '', f)
  return map
})

const fallbackTitle = computed(() => {
  if (props.title) return props.title
  const uk = resolvedKey.value || props.uukey || ''
  return uk ? `${t('widget.detail') || '详情'} · ${uk}` : t('widget.detail') || '详情'
})

const visibleFields = computed(() => formVisibleFields(fields.value))

function pickValue(key: string) {
  const row = values.value || {}
  if (key in row) return row[key]
  return undefined
}

function displayOf(f: SchemaField) {
  return displayFieldValue(values.value || {}, f, { refers: refers.value })
}

function relatedDisplay(row: Record<string, unknown>, f: SchemaField) {
  return displayFieldValue(row, f, { refers: relatedRefers.value })
}

const headTitle = computed(() => {
  const key = props.config.head?.title
  if (!key) return fallbackTitle.value
  return String(pickValue(key) || fallbackTitle.value)
})

const headSubtitle = computed(() => {
  const key = props.config.head?.subtitle
  if (!key) return ''
  return String(pickValue(key) || '')
})

const headBadge = computed(() => {
  const key = props.config.head?.badge
  if (!key) return ''
  const f = fieldByKey.value.get(key)
  if (f) return displayOf(f) || ''
  return String(pickValue(key) || '')
})

const headFields = computed(() => {
  const keys = props.config.head?.fields || []
  return keys.map((k) => fieldByKey.value.get(k)).filter(Boolean) as SchemaField[]
})

const tabs = computed((): RecordEntityTab[] => {
  const list = props.config.tabs || []
  if (list.length) return list
  return [{ id: 'overview', label: t('widget.cardOverview') || '概要', kind: 'fields' }]
})

const activeTabDef = computed(() => tabs.value.find((x) => x.id === activeTab.value) || tabs.value[0])

const overviewFields = computed(() => {
  const tab = activeTabDef.value
  if (!tab || tab.kind !== 'fields') return []
  const keys = tab.fields
  if (keys?.length) {
    return keys
      .filter((k) => k !== '---' && k !== '|')
      .map((k) => fieldByKey.value.get(k))
      .filter(Boolean) as SchemaField[]
  }
  return visibleFields.value
})

/** fields 列表可用 `---` / `|` 插入分割线 */
const overviewBlocks = computed(() => {
  const tab = activeTabDef.value
  if (!tab || tab.kind !== 'fields') return [] as Array<{ type: 'fields'; fields: SchemaField[] } | { type: 'divider' }>
  const keys = tab.fields
  if (!keys?.length) {
    return [{ type: 'fields' as const, fields: visibleFields.value }]
  }
  const blocks: Array<{ type: 'fields'; fields: SchemaField[] } | { type: 'divider' }> = []
  let buf: SchemaField[] = []
  const flush = () => {
    if (!buf.length) return
    blocks.push({ type: 'fields', fields: buf })
    buf = []
  }
  for (const k of keys) {
    if (k === '---' || k === '|') {
      flush()
      if (blocks.length && blocks[blocks.length - 1].type !== 'divider') {
        blocks.push({ type: 'divider' })
      }
      continue
    }
    const f = fieldByKey.value.get(k)
    if (f) buf.push(f)
  }
  flush()
  return blocks
})

const footActions = computed(() => props.config.actions || [])

async function loadRelated(tab: RecordEntityTab) {
  relatedLoading.value = true
  relatedError.value = ''
  relatedRows.value = []
  relatedFields.value = []
  relatedRefers.value = {}
  try {
    const model = String(tab.model || '').trim()
    if (!model) throw new Error('missing related model')
    const using = tab.using || 'default'
    const query: Record<string, unknown> = { ...(tab.query || {}) }
    const fromKey = String(tab.queryFrom || 'basic.uukey')
    const toKey = String(tab.queryKey || 'basic.uukey')
    const fromVal = pickValue(fromKey)
    if (Array.isArray(fromVal)) {
      const ids = fromVal.map((v) => String(v ?? '').trim()).filter(Boolean)
      if (!ids.length) return
      query[`${toKey}:IN`] = ids
    } else if (fromVal != null && String(fromVal).trim() !== '') {
      query[toKey] = fromVal
    }
    const schema = await fetchSchema(model, using, 'SEARCH')
    const allFields = schema.table?.fields || []
    const want = tab.fields?.length
      ? tab.fields.map((k) => allFields.find((f) => f.uukey === k)).filter(Boolean)
      : allFields.slice(0, 5)
    relatedFields.value = want as SchemaField[]
    const res = await searchRecords(model, using, 1, 50, { query })
    relatedRows.value = res.values || []
    relatedRefers.value = normalizeReferDict(res.refers)
  } catch (e) {
    relatedError.value = e instanceof Error ? e.message : String(e)
  } finally {
    relatedLoading.value = false
  }
}

async function ensureFormFields() {
  if (formFields.value.length) return
  const schema = await fetchSchema(props.model, 'default', 'SEARCH')
  formFields.value = schema.table?.fields || fields.value
}

async function load() {
  if (!props.model) return
  loading.value = true
  error.value = ''
  fields.value = []
  values.value = null
  resolvedKey.value = ''
  activeTab.value = ''
  relatedRows.value = []
  formOpen.value = false
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
    resolvedKey.value = uk
    oplogApi?.setTarget(props.model, uk)
    const res = await fetchInputSchema(props.model, 'default', 'DETAIL', uk)
    fields.value = res.input?.fields || []
    if (res.input?.values) values.value = res.input.values as Record<string, unknown>
    refers.value = normalizeReferDict(res.input?.refers as ReferDict)
    if (!values.value) {
      const found = await searchRecords(props.model, 'default', 1, 1, {
        query: { 'basic.uukey': uk },
      })
      values.value = (found.values || [])[0] || { 'basic.uukey': uk }
      refers.value = normalizeReferDict(found.refers)
    }
    activeTab.value = (props.config.tabs || [])[0]?.id || 'overview'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    oplogApi?.clearTarget()
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.model, props.uukey, JSON.stringify(props.lookup || {}), props.config] as const,
  () => {
    void load()
  },
  { immediate: true },
)

watch(
  () => [activeTab.value, values.value] as const,
  () => {
    const tab = activeTabDef.value
    if (!tab || tab.kind !== 'relation') return
    void loadRelated(tab)
  },
)

async function onAction(act: RecordEntityAction) {
  if (act.disabled) return
  const action = String(act.action || act.id || '')
  if (action === 'record.edit' || act.id === 'edit') {
    await ensureFormFields()
    formOpen.value = true
    return
  }
  emit('action', {
    id: act.id,
    action: act.action,
    model: props.model,
    uukey: resolvedKey.value,
  })
}

function onFormSaved() {
  formOpen.value = false
  void load()
}
</script>

<template>
  <div class="entity-card">
    <p v-if="loading" class="muted pad">{{ t('widget.loading') }}</p>
    <p v-else-if="error" class="error pad">{{ error }}</p>
    <template v-else>
      <slot
        name="head"
        :title="headTitle"
        :subtitle="headSubtitle"
        :badge="headBadge"
        :fields="headFields"
        :values="values"
      >
        <section class="ec-head">
          <div class="ec-head-row">
            <div class="ec-head-main min0">
              <div class="ec-title truncate">{{ headTitle }}</div>
              <div v-if="headSubtitle" class="ec-sub muted truncate">{{ headSubtitle }}</div>
            </div>
            <span v-if="headBadge" class="ec-badge">{{ headBadge }}</span>
          </div>
          <RecordFields
            v-if="headFields.length"
            class="ec-head-fields"
            :fields="headFields"
            :display-of="displayOf"
          />
        </section>
      </slot>

      <nav v-if="tabs.length > 1" class="ec-tabs" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="ec-tab"
          :class="{ active: activeTabDef?.id === tab.id }"
          role="tab"
          :aria-selected="activeTabDef?.id === tab.id"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>

      <section class="ec-body pad">
        <slot
          name="body"
          :tab="activeTabDef"
          :values="values"
          :fields="overviewFields"
        >
          <template v-if="activeTabDef?.kind === 'fields'">
            <div class="ec-field-blocks">
              <template v-for="(block, idx) in overviewBlocks" :key="idx">
                <hr v-if="block.type === 'divider'" class="ec-divider" />
                <RecordFields
                  v-else
                  :fields="block.fields"
                  :display-of="displayOf"
                />
              </template>
            </div>
          </template>
          <template v-else-if="activeTabDef?.kind === 'relation'">
            <p v-if="relatedLoading" class="muted">{{ t('widget.loading') }}</p>
            <p v-else-if="relatedError" class="error">{{ relatedError }}</p>
            <p v-else-if="!relatedRows.length" class="muted">
              {{ t('widget.cardNoRelated') }}
            </p>
            <div v-else class="ec-related">
              <table>
                <thead>
                  <tr>
                    <th v-for="f in relatedFields" :key="f.uukey">
                      {{ f.label || f.field }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, idx) in relatedRows" :key="rowUUKey(row) || idx">
                    <td v-for="f in relatedFields" :key="f.uukey">
                      {{ relatedDisplay(row, f) || '—' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </slot>
      </section>

      <footer v-if="footActions.length || $slots.foot" class="ec-foot">
        <slot name="foot" :actions="footActions" :on-action="onAction">
          <button
            v-for="act in footActions"
            :key="act.id"
            type="button"
            class="btn"
            :class="act.variant || ''"
            :disabled="!!act.disabled"
            :title="act.disabled ? act.hint || t('widget.cardDraftHint') : act.hint || ''"
            @click="onAction(act)"
          >
            {{ act.label }}
          </button>
        </slot>
      </footer>
    </template>

    <RecordDialog
      :open="formOpen"
      :model="model"
      using="default"
      :fields="formFields"
      mode="modify"
      :row="values"
      @close="formOpen = false"
      @saved="onFormSaved"
    />
  </div>
</template>

<style scoped>
.entity-card {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  width: 100%;
  min-height: 100%;
  flex: 1 1 auto;
}
.pad {
  padding: 0 16px 16px;
}
.min0 {
  min-width: 0;
}
.ec-head {
  flex-shrink: 0;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--line, #e2e6eb);
}
.ec-head-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.ec-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--ink, #1c1914);
}
.ec-sub {
  margin-top: 2px;
  font-size: 12px;
}
.ec-badge {
  flex-shrink: 0;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--line, #e2e6eb);
  background: color-mix(in srgb, var(--panel, #fff) 88%, var(--ink, #1c1914));
}
.ec-head-fields {
  margin-top: 12px;
}
.ec-tabs {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  padding: 8px 12px 0;
  border-bottom: 1px solid var(--line, #e2e6eb);
  overflow-x: auto;
}
.ec-tab {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--muted, #6b6458);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
}
.ec-tab.active {
  color: var(--ink, #1c1914);
  border-bottom-color: var(--ink, #1c1914);
  font-weight: 600;
}
.ec-body {
  flex: 1 1 auto;
  min-height: 0;
  padding-top: 12px;
}
.ec-field-blocks {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ec-divider {
  border: 0;
  border-top: 1px solid var(--line, #e2e6eb);
  margin: 2px 0;
}
.ec-related {
  overflow: auto;
}
.ec-related table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.ec-related th,
.ec-related td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  vertical-align: top;
}
.ec-related th {
  color: var(--muted, #6b6458);
  font-weight: 500;
}
.ec-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  margin-top: auto;
  position: sticky;
  bottom: 0;
  z-index: 2;
  padding: 10px 16px;
  border-top: 1px solid var(--line, #e2e6eb);
  background: var(--panel, #fff);
}
.muted {
  color: var(--muted, #6b6458);
}
.error {
  color: #b42318;
}
</style>
