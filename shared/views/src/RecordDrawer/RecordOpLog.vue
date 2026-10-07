<script setup lang="ts">
/**
 * Record modification timeline (base.oplog), aligned with duolali RecordOpLog.
 */
import { computed, ref, watch } from 'vue'
import {
  fetchRecordOplogs,
  fetchSchema,
  useI18n,
  type RecordOplogItem,
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

const opLabel: Record<string, string> = {
  INSERT: 'widget.opInsert',
  UPDATE: 'widget.opUpdate',
  DELETE: 'widget.opDelete',
}

function plainLabel(raw: unknown, fallback: string) {
  const text = String(raw || '').replaceAll('|', '').trim()
  return text || fallback
}

function labelOf(key: string) {
  return fieldLabel.value[key] || key
}

function fmtRaw(raw: unknown): string {
  if (raw === undefined || raw === null || raw === '') return t('widget.emptyValue')
  if (typeof raw === 'object') {
    try {
      return JSON.stringify(raw)
    } catch {
      return String(raw)
    }
  }
  return String(raw)
}

function compactDiff(item: RecordOplogItem): string {
  const diff = item.values?.diff
  if (!diff || typeof diff !== 'object') return '—'
  const keys = Object.keys(diff)
  if (!keys.length) return '—'
  const action = String(item.action || '').toUpperCase()
  return keys
    .map((key) => {
      const cell = diff[key] || {}
      const a = fmtRaw(cell.old)
      const b = fmtRaw(cell.new)
      if (action === 'INSERT') return `${labelOf(key)}: ${b}`
      if (action === 'DELETE') return `${labelOf(key)}: ${a}`
      return `${labelOf(key)}: ${a}=>${b}`
    })
    .join('; ')
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function stampOf(item: RecordOplogItem): string {
  const when = formatTime(item.utime || item.created_at)
  const action = String(item.action || '').toUpperCase()
  const op = opLabel[action] ? t(opLabel[action]) : action || '—'
  const actor = item.values?.actor
  const who = actor !== undefined && actor !== null && actor !== '' ? String(actor) : ''
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
    const map: Record<string, string> = {}
    const remember = (key: unknown, label: unknown) => {
      const k = String(key || '').trim()
      if (!k) return
      map[k] = plainLabel(label, k)
    }
    const source = sk?.source?.fields
    if (source) {
      for (const [key, f] of Object.entries(source)) {
        remember(key, f?.label)
        remember(f?.uukey, f?.label)
        remember(f?.index, f?.label)
      }
    }
    for (const f of (sk?.table?.fields || []) as SchemaField[]) {
      if (f?.uukey && !map[f.uukey]) remember(f.uukey, f.label)
      if (f?.index && !map[f.index]) remember(f.index, f.label)
    }
    fieldLabel.value = map
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
