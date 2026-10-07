<template>
  <section class="workspace schema-view" :class="{ 'schema-view--bare': bare }">
    <div v-if="!bare" class="ws-head">
      <div class="ws-title-row">
        <div class="ws-title-block">
          <h1>{{ pageTitle }}{{ viewModeLabel }}</h1>
          <nav
            v-if="viewMode === 'table' && resolvedTabs.length > 1"
            class="ws-tabs"
            aria-label="views"
          >
            <button
              v-for="tab in resolvedTabs"
              :key="`${tab.model}:${tab.using || 'table'}`"
              type="button"
              class="ws-tab"
              :class="{
                active:
                  activeModel === tab.model &&
                  activeUsing === (tab.using || 'table'),
              }"
              @click="selectTab(tab.model, tab.using || 'table')"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>
        <div v-if="viewMode !== 'table'" class="ws-sheet-actions">
          <button type="button" class="btn" @click="exitSheet">
            {{ t('widget.backList') }}
          </button>
        </div>
        <div v-else-if="showBatchEdit" class="ws-sheet-actions">
          <button type="button" class="btn" @click="enterSheet('modify')">
            {{ t('widget.batchMaintain') }}
          </button>
        </div>
      </div>
    </div>

    <p v-if="bootError" class="error">{{ bootError }}</p>
    <p v-if="sheetError" class="error">{{ sheetError }}</p>
    <p v-if="sheetMessage" class="muted pad-msg">{{ sheetMessage }}</p>

    <input
      ref="csvInputRef"
      type="file"
      accept=".csv,text/csv"
      class="hidden-file"
      @change="onCsvPicked"
    />

    <SchemaTable
      v-if="table"
      :key="`${activeModel}:${activeUsing}`"
      ref="tableRef"
      :table="table"
      :using="activeUsing"
      :hide-body="viewMode !== 'table'"
      :hide-pagination="viewMode === 'import'"
      :hide-filter="viewMode === 'import'"
      @button-click="onButtonClick"
      @action-click="onActionClick"
      @record-click="onRecordClick"
      @request-change="onTableRequestChange"
      @refresh="onSheetRefresh"
    >
      <template v-if="viewMode !== 'table'" #toolbar-extra>
        <button
          type="button"
          class="btn primary"
          :disabled="sheetBusy"
          @click="onSheetSave"
        >
          {{ sheetBusy ? t('widget.saving') : t('widget.save') }}
        </button>
        <button
          v-if="showBatchImport"
          type="button"
          class="btn"
          :disabled="sheetBusy"
          @click="onAddN"
        >
          {{ t('widget.addNRows') }}
        </button>
        <button
          v-if="showBatchImport"
          type="button"
          class="btn"
          :disabled="sheetBusy"
          @click="onImportExcel"
        >
          {{ t('widget.importExcel') }}
        </button>
        
      </template>
    </SchemaTable>

    <SchemaSheet
      v-if="table && sheetTable && (viewMode === 'modify' || viewMode === 'import')"
      :key="`sheet-${activeModel}-${sheetTable.using || 'sheet'}-${viewMode}`"
      ref="sheetRef"
      class="sheet-pane"
      :table="sheetTable"
      :request="sheetRequest"
      :mode="viewMode"
    />

    <RecordDialog
      :open="formOpen"
      :model="formModel"
      :using="formUsing"
      :title="formTitle"
      :mode="formMode"
      :row="formRow"
      @close="closeForm"
      @saved="onFormSaved"
    />

    <RecordDrawer
      :open="drawerOpen"
      :title="drawerTitle"
      :wide="!!drawerView"
      :model="drawerModel"
      :uukey="drawerUukey || undefined"
      @close="closeDrawer"
    >
      <slot
        v-if="$slots['record-drawer']"
        name="record-drawer"
        :model="drawerModel"
        :uukey="drawerUukey || undefined"
        :lookup="drawerLookup"
        :title="drawerTitle"
        :close="closeDrawer"
      />
      <component
        v-else
        :is="drawerView || RecordFlatDetail"
        :model="drawerModel"
        :uukey="drawerUukey || undefined"
        :lookup="drawerLookup"
        :title="drawerTitle"
        @close="closeDrawer"
      />
    </RecordDrawer>

    <TableDrawer
      :open="drillOpen"
      :title="drillTitle"
      :model="drillModel"
      :using="drillUsing"
      :fixed-query="drillQuery"
      @close="closeDrill"
    />
  </section>
</template>

<script setup lang="ts">
/**
 * Schema list screen: tabs, table, sheet, form, and record drawer.
 * Lives in @modoor/views because it loads schema from the API.
 * Module pages may override via handlers (e.g. freight full-page builder).
 */
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import {
  appConfirm,
  appToast,
  post,
  entityLabel,
  fetchSchema,
  resolveModelTitle,
  rememberModelTitle,
  invokeRecordHandles,
  rowUUKey, useI18n,
  type SchemaClick,
  type SchemaRequest,
  type SchemaTable as SchemaTableData,
} from '@modoor/hooks'
import { SchemaTable } from '@modoor/widget/SchemaTable'
import RecordDialog from '../RecordDialog/RecordDialog.vue'
import RecordDrawer, { RecordFlatDetail, resolveRecordView } from '../RecordDrawer'
import TableDrawer from '../TableDrawer'

export type SchemaViewTab = {
  model: string
  label: string
  using?: string
}

export type SchemaViewHandlers = {
  /** 返回 true 表示已处理，表格不再打开默认新建框。 */
  'record.create'?: (ctx?: { using?: string }) => boolean | void
  /** 返回 true 表示已处理；返回 false 时关联字段仍走默认抽屉。 */
  'record.open'?: (payload: {
    model: string
    uukey?: string
    lookup?: Record<string, unknown>
    title?: string
    intent?: 'detail' | 'modify'
    record?: Record<string, unknown>
  }) => boolean | void
}

const { t } = useI18n()

const SchemaSheet = defineAsyncComponent(() =>
  import('@modoor/widget/SchemaSheet').then((m) => m.SchemaSheet),
)

const props = withDefaults(
  defineProps<{
    title?: string
    tabs?: SchemaViewTab[]
    model?: string
    using?: string
    handlers?: SchemaViewHandlers
    /** 固定查询，合并进列表 request.query。 */
    query?: Record<string, unknown>
    /** 嵌在别的页面里时不显示标题行。 */
    bare?: boolean
  }>(),
  {
    title: '',
    tabs: () => [],
    model: '',
    using: 'table',
    bare: false,
  },
)

const emit = defineEmits<{
  'button-click': [
    payload: { click: SchemaClick; keys: string[]; records: Record<string, unknown>[] },
  ]
  'action-click': [payload: { click: SchemaClick; record: Record<string, unknown>; key: string }]
  'record-click': [
    payload: {
      model: string
      uukey?: string
      title?: string
      record?: Record<string, unknown>
      lookup?: Record<string, unknown>
    },
  ]
}>()

const resolvedTabs = computed((): SchemaViewTab[] => {
  if (props.tabs.length > 0) return props.tabs
  if (props.model) {
    return [
      {
        model: props.model,
        label: props.title || props.model,
        using: props.using || 'table',
      },
    ]
  }
  return []
})

const activeModel = ref('')
const activeUsing = ref('table')
const table = ref<SchemaTableData | null>(null)
/** 批量编辑/导入专用 schema（tables.json → using=sheet） */
const sheetSchema = ref<SchemaTableData | null>(null)
const schemaTitle = ref('')
/** 页签切换不改大标题；只在进入新页面时重新取一次。 */
const pinnedTitle = ref('')
const bootError = ref('')
const tableRef = ref<{
  reload: () => Promise<void>
  getListRequest?: () => {
    page: number
    size: number
    query?: Record<string, unknown>
    order?: { field: string; order: string }
  }
  getSelectedRows: () => Record<string, unknown>[]
  getSelectedKeys: () => string[]
  exportByQuery: () => Promise<void>
  exportSelected: () => Promise<void>
  deleteSelected: () => Promise<void>
} | null>(null)
const sheetRef = ref<{
  reload: () => Promise<void>
  whenReady?: () => Promise<void>
  addRows?: (n?: number) => Promise<void>
  importMappedRows?: (headers: string[], dataRows: string[][]) => Promise<void>
  saveAll: () => Promise<void>
  collectRows?: () => Record<string, string>[]
  saving: boolean
  error: string
  message: string
} | null>(null)
const csvInputRef = ref<HTMLInputElement | null>(null)

type ViewMode = 'table' | 'modify' | 'import'
const viewMode = ref<ViewMode>('table')
const listRequest = ref<{
  page: number
  size: number
  query?: Record<string, unknown>
}>({ page: 1, size: 50 })

const sheetCaps = computed(() => {
  const raw = table.value?.sheet ?? (table.value?.others?.sheet as unknown)
  const list = Array.isArray(raw) ? raw.map(String) : []
  return new Set(list.map((s) => s.trim().toLowerCase()))
})
const showBatchEdit = computed(() => sheetCaps.value.has('update'))
const showBatchImport = computed(() => sheetCaps.value.has('insert'))

const actionOpen = ref(false)
const actionModel = ref('')
const actionUsing = ref('default')
const actionTitle = ref('')
const actionDefaults = ref<Record<string, unknown> | null>(null)

/** Generic create/edit RecordDialog (table toolbar / row edit). Shares UI with domain actions. */
const recordFormOpen = ref(false)
const recordFormMode = ref<'create' | 'modify'>('create')
const recordFormRow = ref<Record<string, unknown> | null>(null)

const formOpen = computed(() => actionOpen.value || recordFormOpen.value)
const formModel = computed(() =>
  actionOpen.value ? actionModel.value || activeModel.value : activeModel.value,
)
const formUsing = computed(() =>
  actionOpen.value ? actionUsing.value : activeUsing.value,
)
const formTitle = computed(() => (actionOpen.value ? actionTitle.value : ''))
const formMode = computed((): 'create' | 'modify' =>
  actionOpen.value ? 'create' : recordFormMode.value,
)
const formRow = computed(() =>
  actionOpen.value ? actionDefaults.value : recordFormRow.value,
)

const drawerOpen = ref(false)
const drawerModel = ref('')
const drawerUukey = ref('')
const drawerLookup = ref<Record<string, unknown> | undefined>()
const drawerTitle = ref('')
const drawerView = computed(() =>
  drawerOpen.value ? resolveRecordView(drawerModel.value) : undefined,
)

/** DIGEST 行「明细」→ TableDrawer 下钻 */
const drillOpen = ref(false)
const drillTitle = ref('')
const drillModel = ref('')
const drillUsing = ref('default')
const drillQuery = ref<Record<string, unknown>>({})

const pageTitle = computed(() => {
  if (props.title) return props.title
  return pinnedTitle.value || schemaTitle.value || activeModel.value
})

const viewModeLabel = computed(() => {
  if (viewMode.value === 'modify') return t('widget.batchEditSuffix')
  if (viewMode.value === 'import') return t('widget.batchImportSuffix')
  return ''
})

const sheetTable = computed((): SchemaTableData | null => {
  const list = table.value
  if (!list) return null
  const cur = sheetSchema.value || list
  return {
    model: cur.model || list.model,
    using: cur.using || 'sheet',
    title: cur.title || list.title,
    fields: cur.fields,
    sticky: cur.sticky,
    refers: cur.refers || list.refers,
    sheet: list.sheet ?? cur.sheet,
    others: cur.others,
  }
})

const sheetRequest = computed((): SchemaRequest => {
  if (viewMode.value === 'modify') {
    return {
      page: listRequest.value.page || 1,
      size: listRequest.value.size || 50,
      query: listRequest.value.query ?? table.value?.request?.query,
    }
  }
  return {
    page: 1,
    size: 50,
    query: table.value?.request?.query,
  }
})

const sheetBusy = computed(() => !!sheetRef.value?.saving)
const sheetError = computed(() => sheetRef.value?.error || '')
const sheetMessage = computed(() => sheetRef.value?.message || '')

function onTableRequestChange(req: {
  page: number
  size: number
  query?: Record<string, unknown>
}) {
  listRequest.value = {
    page: req.page || 1,
    size: req.size || 50,
    query: req.query,
  }
  if (viewMode.value === 'modify') {
    void nextTick(() => sheetRef.value?.reload())
  }
}

async function boot(model: string, usingKey: string) {
  if (!model) return
  bootError.value = ''
  viewMode.value = 'table'
  table.value = null
  sheetSchema.value = null
  listRequest.value = { page: 1, size: 50 }
  closeForm()
  closeDrawer()
  try {
    const res = await fetchSchema(model, usingKey)
    const fixed = props.query || {}
    table.value = {
      ...res.table,
      model: res.model,
      using: res.using,
      sheet: res.table.sheet,
      others: res.table.others,
      request: {
        ...(res.table.request || {}),
        query: { ...(res.table.request?.query || {}), ...fixed },
      },
    }
    const nextTitle = res.table.title || res.model
    schemaTitle.value = nextTitle
    rememberModelTitle(res.model, nextTitle)
    if (!pinnedTitle.value) pinnedTitle.value = nextTitle
  } catch (e) {
    bootError.value = e instanceof Error ? e.message : String(e)
  }
}

function selectTab(model: string, usingKey = 'table') {
  if (model === activeModel.value && usingKey === activeUsing.value) return
  activeModel.value = model
  activeUsing.value = usingKey
}

async function loadSheetSchema() {
  const model = activeModel.value
  if (!model) return
  try {
    const res = await fetchSchema(model, 'sheet')
    sheetSchema.value = {
      ...res.table,
      model: res.model,
      using: res.using || 'sheet',
      sheet: res.table.sheet,
      others: res.table.others,
    }
  } catch (e) {
    sheetSchema.value = null
    appToast(e instanceof Error ? e.message : String(e), 'error')
  }
}

async function enterSheet(mode: 'modify' | 'import') {
  await loadSheetSchema()
  viewMode.value = mode
}

async function ensureImportMode() {
  const switching = viewMode.value !== 'import'
  const prev = switching ? sheetRef.value : null
  if (switching) {
    await loadSheetSchema()
    viewMode.value = 'import'
  }
  for (let i = 0; i < 40; i++) {
    await nextTick()
    const sheet = sheetRef.value
    if (sheet?.whenReady && sheet !== prev) break
    await new Promise((r) => setTimeout(r, 25))
  }
  await sheetRef.value?.whenReady?.()
}

async function exitSheet() {
  viewMode.value = 'table'
  sheetSchema.value = null
  await tableRef.value?.reload()
}

/** sheet 态刷新：回到 edit 并重新拉数 */
async function onSheetRefresh() {
  if (viewMode.value === 'table') return
  const fromImport = viewMode.value === 'import'
  viewMode.value = 'modify'
  if (fromImport) {
    // key 切换会 remount 并按 sheetRequest 加载
    for (let i = 0; i < 40; i++) {
      await nextTick()
      if (sheetRef.value?.reload) break
      await new Promise((r) => setTimeout(r, 25))
    }
    return
  }
  await sheetRef.value?.reload()
}

async function onSheetSave() {
  await sheetRef.value?.saveAll()
}

async function onAddTen() {
  await ensureImportMode()
  await sheetRef.value?.addRows?.(10)
}

async function onAddN() {
  const raw = window.prompt(t('widget.addRowsPrompt'), '10')
  if (raw == null) return
  const n = Math.floor(Number(raw))
  if (!Number.isFinite(n) || n < 1) {
    appToast(t('widget.addRowsPrompt'), 'error')
    return
  }
  await ensureImportMode()
  await sheetRef.value?.addRows?.(Math.min(n, 100))
}

function onImportExcel() {
  void ensureImportMode().then(() => {
    csvInputRef.value?.click()
  })
}

async function onCsvPicked(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const text = await file.text()
    const { headers, rows } = parseCsv(text)
    if (!rows.length) {
      appToast(t('widget.noExportData'), 'error')
      return
    }
    await sheetRef.value?.importMappedRows?.(headers, rows)
  } catch (e) {
    appToast(e instanceof Error ? e.message : String(e), 'error')
  }
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const lines = text
    .replace(/^\uFEFF/, '')
    .split(/\r?\n/)
    .map((l) => l.trimEnd())
    .filter((l) => l.length)
  if (lines.length < 2) return { headers: [], rows: [] }
  const split = (line: string) => {
    const out: string[] = []
    let cur = ''
    let q = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (ch === '"') {
        if (q && line[i + 1] === '"') {
          cur += '"'
          i++
        } else q = !q
        continue
      }
      if (ch === ',' && !q) {
        out.push(cur)
        cur = ''
        continue
      }
      cur += ch
    }
    out.push(cur)
    return out
  }
  return { headers: split(lines[0]), rows: lines.slice(1).map(split) }
}

function closeAction() {
  actionOpen.value = false
  actionModel.value = ''
  actionUsing.value = 'default'
  actionTitle.value = ''
  actionDefaults.value = null
}

function closeRecordForm() {
  recordFormOpen.value = false
  recordFormMode.value = 'create'
  recordFormRow.value = null
}

function closeForm() {
  closeAction()
  closeRecordForm()
}

function closeDrawer() {
  drawerOpen.value = false
  drawerModel.value = ''
  drawerUukey.value = ''
  drawerLookup.value = undefined
  drawerTitle.value = ''
}

function isCreateClick(c: SchemaClick) {
  const action = String(c.action || '').toUpperCase()
  const uk = String(c.uukey || '').toLowerCase()
  return (
    action === 'RECORD.CREATE' ||
    action === 'INSERT' ||
    action === 'CREATE' ||
    uk === 'create' ||
    uk === 'record.create'
  )
}

function isDeleteClick(c: SchemaClick) {
  const action = String(c.action || '').toUpperCase()
  const uk = String(c.uukey || '').toLowerCase()
  return action === 'RECORD.DELETE' || action === 'DELETE' || uk === 'delete' || uk === 'record.delete'
}

function isExportClick(c: SchemaClick) {
  const action = String(c.action || '').toUpperCase()
  const uk = String(c.uukey || '').toLowerCase()
  return (
    action === 'RECORD.EXPORT' ||
    action === 'EXPORT' ||
    uk === 'export' ||
    uk === '__export__' ||
    uk === 'record.export'
  )
}

function isExportSelectedClick(c: SchemaClick) {
  const action = String(c.action || '').toUpperCase()
  const uk = String(c.uukey || '').toLowerCase()
  return (
    action === 'RECORD.EXPORT.SELECTED' ||
    action === 'EXPORT.SELECTED' ||
    uk === 'export.selected' ||
    uk === 'record.export.selected'
  )
}

function isEditClick(c: SchemaClick) {
  const action = String(c.action || '').toUpperCase()
  const uk = String(c.uukey || '').toLowerCase()
  return (
    action === 'RECORD.MODIFY' ||
    action === 'RECORD.EDIT' ||
    action === 'MODIFY' ||
    action === 'EDIT' ||
    uk === 'modify' ||
    uk === 'edit' ||
    uk === 'record.modify' ||
    uk === 'record.edit'
  )
}

function isDigestDetailClick(c: SchemaClick) {
  const action = String(c.action || '')
  const uk = String(c.uukey || '')
  return action === 'digest.detail' || uk === 'digest.detail'
}

function closeDrill() {
  drillOpen.value = false
  drillModel.value = ''
  drillUsing.value = 'default'
  drillTitle.value = ''
  drillQuery.value = {}
}

function openDigestDrill(row: Record<string, unknown>) {
  const cur = table.value
  if (!cur?.model) return
  const others = (cur.others || {}) as Record<string, unknown>
  const meta = (others.$digest || {}) as {
    group_by?: Array<{ index?: string; format?: string }>
  }
  const groups = Array.isArray(meta.group_by) ? meta.group_by : []
  const q: Record<string, unknown> = { ...(cur.request?.query || {}) }
  const tips: string[] = []
  for (const g of groups) {
    const key = String(g?.index || '').trim()
    if (!key) continue
    const val = row[key]
    if (val == null || val === '') continue
    q[key] = val
    tips.push(String(val))
  }
  drillModel.value = cur.model
  drillUsing.value = 'default'
  drillQuery.value = q
  drillTitle.value = tips.length ? `明细 · ${tips.join(' / ')}` : '明细'
  drillOpen.value = true
}

function openCreateForm() {
  const defaults = (table.value as SchemaTableData & { createDefaults?: Record<string, unknown> })
    ?.createDefaults
  recordFormMode.value = 'create'
  recordFormRow.value =
    defaults && Object.keys(defaults).length ? { ...defaults } : null
  recordFormOpen.value = true
}

function openEditForm(row: Record<string, unknown>) {
  recordFormMode.value = 'modify'
  recordFormRow.value = row
  recordFormOpen.value = true
}

async function openRecordDetail(payload: {
  model: string
  uukey?: string
  lookup?: Record<string, unknown>
  title?: string
  record?: Record<string, unknown>
  intent?: 'detail' | 'modify'
}) {
  const intent = payload.intent || 'detail'
  emit('record-click', payload)
  if (
    props.handlers?.['record.open']?.({ ...payload, intent }) === true ||
    invokeRecordHandles('record.open', { ...payload, intent })
  ) {
    return
  }
  if (payload.intent === 'modify' && payload.record) {
    openEditForm(payload.record)
    return
  }
  drawerModel.value = payload.model
  drawerUukey.value = payload.uukey || ''
  drawerLookup.value = payload.lookup
  const hint =
    payload.model === activeModel.value ? schemaTitle.value || table.value?.title || '' : ''
  drawerTitle.value = entityLabel(await resolveModelTitle(payload.model, hint), payload.model)
  drawerOpen.value = true
}

async function onFormSaved() {
  closeForm()
  await tableRef.value?.reload()
}

function requireOneRow(rows: Record<string, unknown>[]): Record<string, unknown> | null {
  if (rows.length !== 1) {
    appToast(t('widget.pickOneRow'), 'error')
    return null
  }
  return rows[0]
}

async function handleDomainButton(payload: {
  click: SchemaClick
  keys: string[]
  records: Record<string, unknown>[]
}) {
  const action = String(payload.click.action || '')
  const label = payload.click.label || payload.click.uukey

  if (action === 'fleet.salary.sync.current' || action === 'fleet.salary.sync.previous') {
    const period = action.endsWith('previous') ? 'previous' : 'current'
    const ok = await appConfirm(`确认${label}？将按财务期间汇总在职司机的考核工资。`)
    if (!ok) return true
    try {
      const res = await post<{ uterm: number; upserted: number }>('/api/fleet/salary/sync', {
        period,
      })
      appToast(`${label}完成：期间 ${res.uterm}，更新 ${res.upserted} 人`)
      await tableRef.value?.reload()
    } catch (err) {
      appToast(err instanceof Error ? err.message : String(err), 'error')
    }
    return true
  }

  if (
    action === 'fleet.tire.install'
    || action === 'fleet.tire.replace'
    || action === 'fleet.tire.remove'
    || action === 'fleet.tire.scrap'
  ) {
    const row = requireOneRow(payload.records)
    if (!row) return true
    const tireId = rowUUKey(row)
    if (!tireId) {
      appToast(t('widget.pickOneRow'), 'error')
      return true
    }
    const using =
      action === 'fleet.tire.replace'
        ? 'replace'
        : action === 'fleet.tire.remove'
          ? 'remove'
          : action === 'fleet.tire.scrap'
            ? 'scrap'
            : 'install'
    actionModel.value = 'fleet.tirelog'
    actionUsing.value = using
    actionTitle.value = label
    actionDefaults.value = {
      'basic.tire': tireId,
      'basic.event_type': using,
    }
    actionOpen.value = true
    return true
  }

  if (action === 'fleet.tire.register') {
    const row = requireOneRow(payload.records)
    if (!row) return true
    const tireId = rowUUKey(row)
    if (!tireId) {
      appToast(t('widget.pickOneRow'), 'error')
      return true
    }
    actionModel.value = 'fleet.tiremile'
    actionUsing.value = 'default'
    actionTitle.value = label
    actionDefaults.value = {
      'basic.tire': tireId,
      'basic.source': 'manual',
    }
    actionOpen.value = true
    return true
  }

  if (action === 'fleet.product.inbound' || action === 'fleet.product.outbound') {
    const row = requireOneRow(payload.records)
    if (!row) return true
    const productId = rowUUKey(row)
    if (!productId) {
      appToast(t('widget.pickOneRow'), 'error')
      return true
    }
    const kind = action === 'fleet.product.inbound' ? 'inbound' : 'outbound'
    actionModel.value = 'fleet.oplog'
    actionUsing.value = kind
    actionTitle.value = label
    actionDefaults.value = {
      'basic.product': productId,
      'basic.type': kind,
      'basic.price': row['basic.price'] ?? row.price ?? '',
      'basic.warehouse': row['basic.warehouse'] ?? row.warehouse ?? '',
    }
    actionOpen.value = true
    return true
  }
  return false
}

async function onButtonClick(payload: {
  click: SchemaClick
  keys: string[]
  records: Record<string, unknown>[]
}) {
  emit('button-click', payload)
  if (isCreateClick(payload.click)) {
    const extra = (payload.click.extra || {}) as { using?: string }
    const picked = String(payload.click.using || extra.using || '').trim()
    const using = picked || activeUsing.value
    if (
      props.handlers?.['record.create']?.({ using }) === true ||
      invokeRecordHandles('record.create', {
        model: activeModel.value,
        using,
        click: { uukey: payload.click.uukey, action: payload.click.action, using },
      })
    ) {
      return
    }
    openCreateForm()
    return
  }
  if (isDeleteClick(payload.click)) {
    await tableRef.value?.deleteSelected()
    return
  }
  if (isExportSelectedClick(payload.click)) {
    await tableRef.value?.exportSelected()
    return
  }
  if (isExportClick(payload.click)) {
    await tableRef.value?.exportByQuery()
    return
  }
  if (await handleDomainButton(payload)) return
}

function onActionClick(payload: {
  click: SchemaClick
  record: Record<string, unknown>
  key: string
}) {
  emit('action-click', payload)
  if (isDigestDetailClick(payload.click)) {
    openDigestDrill(payload.record)
    return
  }
  if (isEditClick(payload.click)) {
    const uk = rowUUKey(payload.record) || payload.key
    openRecordDetail({
      model: activeModel.value,
      uukey: uk || undefined,
      title: uk || undefined,
      record: payload.record,
      intent: 'modify',
    })
    return
  }
  // Domain row actions: reuse domain button handler with single-row selection.
  void handleDomainButton({
    click: payload.click,
    keys: payload.key ? [payload.key] : [],
    records: [payload.record],
  })
}

function onRecordClick(payload: {
  model: string
  uukey?: string
  lookup?: Record<string, unknown>
  title?: string
  record?: Record<string, unknown>
}) {
  openRecordDetail({ ...payload, intent: 'detail' })
}

function syncActiveFromTabs() {
  const list = resolvedTabs.value
  if (!list.length) {
    activeModel.value = ''
    return
  }
  const hit = list.find((x) => x.model === activeModel.value)
  if (!hit) {
    activeModel.value = list[0].model
    activeUsing.value = list[0].using || 'table'
  } else {
    activeUsing.value = hit.using || activeUsing.value || 'table'
  }
}

watch(
  () => [props.model, props.using, JSON.stringify(props.tabs), props.title] as const,
  () => {
    pinnedTitle.value = ''
    syncActiveFromTabs()
  },
  { immediate: true },
)

watch(
  [activeModel, activeUsing],
  ([m, u]) => {
    if (m) void boot(m, u || 'table')
  },
  { immediate: true },
)

watch(
  () => JSON.stringify(props.query || {}),
  () => {
    if (activeModel.value) void boot(activeModel.value, activeUsing.value || 'table')
  },
)
</script>

<style scoped>
.schema-view--bare {
  box-shadow: none;
  border: none;
  background: transparent;
  border-radius: 0;
  min-height: 360px;
}
.ws-head {
  padding-bottom: 0;
  border-bottom: 1px solid var(--line, #e2e6eb);
}
.ws-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.ws-title-block {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: 0.75rem;
  min-width: 0;
  flex-wrap: wrap;
}
.ws-title-block h1 {
  margin: 0;
  padding-bottom: 0.5rem;
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.2;
}
.ws-tabs {
  display: flex;
  gap: 0;
  flex-wrap: wrap;
  align-items: flex-end;
}
.ws-tab {
  font: inherit;
  font-size: 0.9rem;
  line-height: 1.2;
  padding: 0.5rem 1rem;
  margin-bottom: -1px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted, #6b6458);
  cursor: pointer;
  transition: color 0.12s ease, border-color 0.12s ease;
}
.ws-tab:hover {
  color: var(--ink, #1c1914);
}
.ws-tab.active {
  color: var(--accent, #0f6a5a);
  font-weight: 600;
  border-bottom-color: var(--accent, #0f6a5a);
  background: transparent;
}
.ws-tab:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent, #0f6a5a) 40%, transparent);
  outline-offset: 2px;
}
.ws-sheet-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 0.45rem;
}
.ws-sheet-actions .btn {
  font: inherit;
  font-size: 0.875rem;
  line-height: 1.1;
  padding: 5px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line, #e2e6eb);
  background: #fff;
  cursor: pointer;
}
.ws-sheet-actions .btn.primary {
  background: var(--accent, #0f6a5a);
  border-color: var(--accent, #0f6a5a);
  color: #fff;
}
.ws-sheet-actions .btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.hidden-file {
  display: none;
}
.pad-msg {
  padding: 0 16px 8px;
  font-size: 0.85rem;
}
.sheet-pane {
  flex: 1;
  min-height: 0;
}
.error {
  color: #b91c1c;
  margin: 0 16px 0.5rem;
}
.muted {
  color: var(--muted, #78716c);
}
</style>
