<script setup lang="ts">
/**
 * 字段设置：低表覆盖 config.json 的 label / formula / display，并控制显隐。
 * 存 base_cfg：mod=fleet / freight · type=fields
 */
import { computed, onMounted, ref } from 'vue'
import { appToast } from '@modoor/hooks'

async function readApiError(res: Response): Promise<string> {
  const text = await res.text()
  try {
    const body = JSON.parse(text) as { detail?: { message?: string }; message?: string }
    const msg = body?.detail?.message || body?.message
    if (msg) return String(msg)
  } catch {
    /* keep raw text */
  }
  return text || `请求失败 (${res.status})`
}

const props = withDefaults(
  defineProps<{
    endpoint?: string
  }>(),
  {
    endpoint: '/api/fleet/field-settings',
  },
)

type FieldRow = {
  key: string
  label: string
  formula: string
  display: string
  enabled: boolean
  defaultLabel: string
  defaultFormula: string
  defaultDisplay: string
}
type Group = { model: string; title: string; fields: FieldRow[] }

const loading = ref(false)
const saving = ref(false)
const groups = ref<Group[]>([])

const editor = ref<{
  model: string
  title: string
  draft: FieldRow
} | null>(null)

/** Replace dotted field keys with labels: basic.performance+1 → 绩效+1 */
function formulaToDisplay(formula: string, labels: Record<string, string>) {
  const code = String(formula || '').trim()
  if (!code) return ''
  return code.replace(
    /\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b/g,
    (key) => String(labels[key] || '').trim() || key,
  )
}

function labelsForModel(model: string, draft?: FieldRow | null) {
  const group = groups.value.find((item) => item.model === model)
  const out: Record<string, string> = {}
  for (const field of group?.fields || []) {
    out[field.key] = field.label
  }
  if (draft?.key) out[draft.key] = draft.label.trim() || draft.defaultLabel
  return out
}

const editorDisplay = computed(() => {
  if (!editor.value) return ''
  return formulaToDisplay(editor.value.draft.formula, labelsForModel(editor.value.model, editor.value.draft))
})

function mapGroups(raw: unknown): Group[] {
  if (!Array.isArray(raw)) return []
  return raw.map((group: Group) => ({
    model: String(group.model || ''),
    title: String(group.title || group.model || ''),
    fields: Array.isArray(group.fields)
      ? group.fields.map((field) => ({
          key: String(field.key || ''),
          label: String(field.label || field.key || ''),
          formula: String(field.formula || ''),
          display: String(field.display || ''),
          defaultLabel: String(field.defaultLabel || field.label || field.key || ''),
          defaultFormula: String(field.defaultFormula || ''),
          defaultDisplay: String(field.defaultDisplay || ''),
          enabled: field.enabled !== false,
        }))
      : [],
  }))
}

function setGroup(model: string, on: boolean) {
  groups.value = groups.value.map((group) =>
    group.model === model
      ? { ...group, fields: group.fields.map((field) => ({ ...field, enabled: on })) }
      : group,
  )
}

function isOverridden(field: FieldRow) {
  return (
    field.label !== field.defaultLabel ||
    field.formula !== field.defaultFormula ||
    !field.enabled
  )
}

function openEditor(group: Group, field: FieldRow) {
  editor.value = {
    model: group.model,
    title: group.title,
    draft: { ...field },
  }
}

function closeEditor() {
  editor.value = null
}

function resetDraft() {
  if (!editor.value) return
  const d = editor.value.draft
  d.label = d.defaultLabel
  d.formula = d.defaultFormula
}

async function confirmEditor() {
  if (!editor.value || saving.value) return
  const { model, draft } = editor.value
  const label = draft.label.trim() || draft.defaultLabel
  const formula = draft.formula
  const labels = labelsForModel(model, { ...draft, label })
  groups.value = groups.value.map((group) => {
    if (group.model !== model) return group
    const nextFields = group.fields.map((field) =>
      field.key === draft.key
        ? { ...field, label, formula }
        : field,
    )
    // Refresh derived display for all formulas in this model (label may have changed).
    for (const field of nextFields) {
      labels[field.key] = field.label
    }
    for (const field of nextFields) {
      field.display = formulaToDisplay(field.formula, labels)
    }
    return { ...group, fields: nextFields }
  })
  editor.value = null
  await save()
}

async function load() {
  loading.value = true
  try {
    const res = await fetch(props.endpoint, { credentials: 'include' })
    if (!res.ok) throw new Error(await readApiError(res))
    const body = await res.json()
    groups.value = mapGroups(body.groups)
  } catch (e) {
    appToast(e instanceof Error ? e.message : String(e), 'error')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const res = await fetch(props.endpoint, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ groups: groups.value }),
    })
    if (!res.ok) throw new Error(await readApiError(res))
    const body = await res.json()
    groups.value = mapGroups(body.groups)
    appToast('已保存。重新打开列表或表单后生效。')
  } catch (e) {
    appToast(e instanceof Error ? e.message : String(e), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="field-settings">
    <div class="ph">
      <p class="muted">
        勾选控制是否使用该字段；点击字段可改名称与公式（覆盖模型配置）。按条件/日期的规则仍在「公式设置」。
      </p>
      <div class="ph-actions">
        <button class="btn primary" type="button" :disabled="saving || loading" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </div>

    <p v-if="loading" class="muted">加载中…</p>

    <div v-else class="kind-list">
      <div v-for="group in groups" :key="group.model" class="kind-group">
        <header class="group-head">
          <strong>{{ group.title }}</strong>
          <div class="group-actions">
            <button class="link" type="button" @click="setGroup(group.model, true)">全选</button>
            <button class="link" type="button" @click="setGroup(group.model, false)">全不选</button>
          </div>
        </header>
        <div class="kind-grid">
          <div
            v-for="field in group.fields"
            :key="field.key"
            class="kind-item"
            :class="{ off: !field.enabled, overridden: isOverridden(field) }"
          >
            <input v-model="field.enabled" type="checkbox" @click.stop />
            <button type="button" class="field-hit" @click="openEditor(group, field)">
              <span class="field-label">{{ field.label }}</span>
              <span v-if="isOverridden(field)" class="badge">已覆盖</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="editor" class="mask" @click.self="closeEditor">
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="field-edit-title">
        <header class="head">
          <div>
            <div id="field-edit-title" class="title">字段设置</div>
            <div class="sub">{{ editor.title }}</div>
          </div>
          <button type="button" class="close" @click="closeEditor">关闭</button>
        </header>
        <div class="body">
          <div class="form-grid">
            <label class="row">
              <span>显示名称</span>
              <input v-model="editor.draft.label" class="inp" />
            </label>
            <label class="row">
              <span>字段标识</span>
              <input class="inp mono" :value="editor.draft.key" readonly />
            </label>
          </div>
          <label class="row">
            <span>公式</span>
            <textarea
              v-model="editor.draft.formula"
              class="inp mono formula"
              rows="4"
              placeholder="留空表示无公式；与默认相同则不写入覆盖"
            />
          </label>
          <p v-if="editorDisplay" class="display-muted">{{ editorDisplay }}</p>
        </div>
        <footer class="foot">
          <button type="button" class="btn" @click="resetDraft">恢复默认</button>
          <div class="actions">
            <button type="button" class="btn" :disabled="saving" @click="closeEditor">取消</button>
            <button type="button" class="btn primary" :disabled="saving" @click="confirmEditor">
              {{ saving ? '保存中…' : '确定' }}
            </button>
          </div>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.field-settings {
  padding: 10px 16px 12px;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}
.ph {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
  flex-shrink: 0;
}
.ph-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.muted {
  margin: 0;
  font-size: 12px;
  color: var(--muted, #6b6458);
}
.kind-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 12px;
  align-content: start;
}
.kind-group {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  padding: 12px 14px;
  background: #fff;
}
.group-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.group-actions {
  display: flex;
  gap: 12px;
}
.link {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--accent, #1a7f64);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  padding: 0;
}
.kind-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px 12px;
}
.kind-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 500;
  font-size: 13px;
}
.kind-item.off .field-label {
  color: var(--muted, #6b6458);
  text-decoration: line-through;
}
.field-hit {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 2px 0;
  margin: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.field-hit:hover .field-label {
  color: var(--accent, #1a7f64);
  text-decoration: underline;
}
.field-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 500;
  color: var(--accent, #1a7f64);
  background: color-mix(in srgb, var(--accent, #1a7f64) 12%, #fff);
  border-radius: 4px;
  padding: 1px 5px;
}
.btn {
  appearance: none;
  border: 1px solid var(--line, #e2e6eb);
  background: #fff;
  color: var(--ink, #1c1914);
  border-radius: 8px;
  padding: 6px 12px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.btn.primary {
  background: var(--accent, #1a7f64);
  border-color: var(--accent, #1a7f64);
  color: #fff;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mask {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: #1c191766;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}
.dialog {
  width: min(92vw, 560px);
  max-height: min(86vh, 720px);
  display: flex;
  flex-direction: column;
  background: var(--panel, #fff);
  color: var(--ink, #1c1914);
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 12px;
  box-shadow: 0 18px 48px #1c191733;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
}
.title {
  font-size: 16px;
  font-weight: 600;
}
.sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--muted, #6b6458);
}
.close {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--muted, #6b6458);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  padding: 2px 4px;
}
.body {
  padding: 4px 16px 12px;
  overflow: auto;
  display: grid;
  gap: 12px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.row {
  display: grid;
  gap: 6px;
  font-size: 13px;
  min-width: 0;
}
.row > span:first-child {
  font-weight: 500;
  min-width: 4rem;
}
.inp {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
  background: #fff;
}
.inp:read-only {
  background: #f6f7f8;
  color: var(--muted, #6b6458);
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}
.formula {
  resize: vertical;
  min-height: 88px;
  line-height: 1.45;
}
.display-muted {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted, #6b6458);
  word-break: break-word;
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--line, #e2e6eb);
}
.actions {
  display: flex;
  gap: 8px;
}
</style>
