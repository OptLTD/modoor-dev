<script setup lang="ts">
/**
 * Record modification timeline (base.oplog), aligned with duolali RecordOpLog.
 */
import { computed, ref, watch } from 'vue'
import {
  displayFieldValue,
  fetchRecordOplogs,
  fetchSchema,
  formatDateTimeDisplay,
  loadDropdownRefers,
  normalizeReferDict,
  useI18n,
  type RecordOplogItem,
  type ReferDict,
  type SchemaField,
} from '@modoor/hooks'

const props = withDefaults(
  defineProps<{
    model: string
    uukey: string
  }>(),
  {},
)

const { t } = useI18n()
const loading = ref(false)
const error = ref('')
const items = ref<RecordOplogItem[]>([])
const fieldLabel = ref<Record<string, string>>({})
const fieldMeta = ref<Record<string, SchemaField>>({})
const refers = ref<ReferDict>({})
const userName = ref<Record<string, string>>({})

const CRUD_OPS = new Set(['INSERT', 'UPDATE', 'DELETE', 'UPSERT'])
const opLabel: Record<string, string> = {
  INSERT: 'widget.opInsert',
  UPDATE: 'widget.opUpdate',
  DELETE: 'widget.opDelete',
}
const actionLabel: Record<string, string> = {
  'freight.recalc': 'widget.opRecalc',
}

function plainLabel(raw: unknown, fallback: string) {
  const text = String(raw || '').replaceAll('|', '').trim()
  return text || fallback
}

function labelOf(key: string) {
  return fieldLabel.value[key] || key
}

function isEmptyRaw(raw: unknown): boolean {
  if (raw === undefined || raw === null || raw === '') return true
  return Array.isArray(raw) && raw.length === 0
}

function fmtRaw(key: string, raw: unknown): string {
  if (isEmptyRaw(raw)) return t('widget.emptyValue')
  const field = fieldMeta.value[key]
  if (field) {
    const row: Record<string, unknown> = { [key]: raw }
    if (field.uukey) row[field.uukey] = raw
    if (field.index) row[field.index] = raw
    if (field.field) row[field.field] = raw
    const shown = displayFieldValue(row, field, { refers: refers.value })
    if (shown !== '') return shown
  }
  if (typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(raw)) {
    return formatDateTimeDisplay(raw) || t('widget.emptyValue')
  }
  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw)
    } catch {
      return String(raw)
    }
  }
  return String(raw)
}

function actionTitle(item: RecordOplogItem): string {
  const act = String(item.action || '')
  if (act && !CRUD_OPS.has(act.toUpperCase())) {
    const key = actionLabel[act] || actionLabel[act.toLowerCase()]
    return key ? t(key) : act
  }
  const upper = act.toUpperCase()
  return opLabel[upper] ? t(opLabel[upper]) : upper || '—'
}

function compactDiff(item: RecordOplogItem): string {
  const note = String(item.values?.note || '').trim()
  if (note) return note
  const diff = item.values?.diff
  if (!diff || typeof diff !== 'object') return '—'
  const keys = Object.keys(diff)
  if (!keys.length) return '—'
  const action = String(item.action || '').toUpperCase()
  const parts = keys
    .map((key) => {
      const cell = diff[key] || {}
      const a = fmtRaw(key, cell.old)
      const b = fmtRaw(key, cell.new)
      if (action === 'INSERT') return `${labelOf(key)}: ${b}`
      if (action === 'DELETE') return `${labelOf(key)}: ${a}`
      if (a === b) return ''
      return `${labelOf(key)}: ${a}=>${b}`
    })
    .filter(Boolean)
  return parts.join('; ') || '—'
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  return formatDateTimeDisplay(iso) || String(iso)
}

function stampOf(item: RecordOplogItem): string {
  const when = formatTime(item.utime || item.created_at)
  const op = actionTitle(item)
  const actor = item.values?.actor
  const who = actor === undefined || actor === null || actor === ''
    ? ''
    : userName.value[String(actor)] || ''
  return [when, who, op].filter(Boolean).join(' ')
}

const sorted = computed(() => {
  const list = [...items.value]
  list.sort((a, b) => {
    const ta = a.utime || a.created_at || ''
    const tb = b.utime || b.created_at || ''
    if (tb !== ta) return tb.localeCompare(ta)
    return String(b.id).localeCompare(String(a.id))
  })
  return list
})

async function load() {
  if (!props.model || !props.uukey) {
    items.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [op, sk] = await Promise.all([
      fetchRecordOplogs(props.model, props.uukey),
      fetchSchema(props.model, 'default', 'DETAIL').catch(() => null),
    ])
    items.value = op.items || []
    const names: Record<string, string> = {}
    for (const u of op.users || []) {
      if (u?.id == null) continue
      names[String(u.id)] = String(u.name || '').trim()
    }
    userName.value = names
    const map: Record<string, string> = {}
    const meta: Record<string, SchemaField> = {}
    const remember = (key: unknown, f: SchemaField | undefined) => {
      const k = String(key || '').trim()
      if (!k || !f) return
      map[k] = plainLabel(f.label, k)
      meta[k] = f
    }
    const source = sk?.source?.fields
    if (source) {
      for (const [key, f] of Object.entries(source)) {
        remember(key, f)
        remember(f?.uukey, f)
        remember(f?.index, f)
      }
    }
    for (const f of (sk?.table?.fields || []) as SchemaField[]) {
      if (f?.uukey && !map[f.uukey]) remember(f.uukey, f)
      if (f?.index && !map[f.index]) remember(f.index, f)
    }
    fieldLabel.value = map
    fieldMeta.value = meta
    refers.value = await loadDropdownRefers(
      Object.values(meta),
      normalizeReferDict(sk?.table?.refers),
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    items.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.model, props.uukey] as const,
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <div class="record-oplog">
    <p v-if="loading" class="muted pad">{{ t('widget.loading') }}</p>
    <p v-else-if="error" class="error pad">{{ error }}</p>
    <p v-else-if="!sorted.length" class="muted pad empty">{{ t('widget.noChangelog') }}</p>
    <ol v-else class="timeline">
      <li v-for="item in sorted" :key="item.id" class="tl-item">
        <div class="tl-dot" aria-hidden="true" />
        <div class="tl-body">
          <div class="tl-stamp">{{ stampOf(item) }}</div>
          <div class="tl-diff">{{ compactDiff(item) }}</div>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.record-oplog {
  min-height: 160px;
  padding: 8px 16px 20px;
}
.pad {
  margin: 12px 0;
}
.muted {
  color: var(--muted, #6b7280);
  font-size: 13px;
}
.error {
  color: var(--err, #9b1c1c);
  font-size: 13px;
}
.empty {
  text-align: center;
  padding: 32px 12px;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 4px 0 0 2px;
}
.tl-item {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 0 0 16px 4px;
}
.tl-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 7px;
  top: 14px;
  bottom: 0;
  width: 1px;
  background: var(--line, #e2e6eb);
}
.tl-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--accent, #0b6e4f) 55%, #fff);
  background: color-mix(in srgb, var(--accent, #0b6e4f) 25%, #fff);
}
.tl-body {
  min-width: 0;
  flex: 1;
}
.tl-stamp {
  font-size: 12px;
  color: var(--muted, #6b7280);
  margin-bottom: 4px;
  line-height: 1.4;
}
.tl-diff {
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink, #1c1914);
  word-break: break-word;
}
</style>
