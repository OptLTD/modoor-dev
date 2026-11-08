<script setup lang="ts">
/**
 * OPTIONAL 字典设置 — 合并 fleet 与 freight（global）两行 base_cfg。
 * 侧栏：左 title，右 key；排除 hidden / *.status（动作绑定或系统态）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { appToast } from '@modoor/hooks'

type DictItem = { uukey: string; value: string; parent: string }
type DictMeta = {
  title?: string
  depends?: string
  hidden?: boolean
  options?: DictItem[]
}

const props = withDefaults(
  defineProps<{
    mods?: string[]
  }>(),
  {
    mods: () => ['fleet'],
  },
)
const CFG_TYPE = 'dict'
const bundle = ref<Record<string, DictMeta>>({})
const sources = ref<Record<string, string>>({})
const activeKey = ref('')
const draft = ref<DictItem[]>([])
const draftTitle = ref('')
const loading = ref(false)
const saving = ref(false)
const q = ref('')

function isHiddenMeta(meta: DictMeta | undefined) {
  return Boolean(meta?.hidden)
}

const items = computed(() =>
  Object.entries(bundle.value)
    .map(([type, meta]) => ({
      type,
      title: String(meta?.title || type),
      depends: String(meta?.depends || '').trim(),
      hidden: isHiddenMeta(meta),
      data: meta?.options || [],
    }))
    .sort((a, b) => a.type.localeCompare(b.type)),
)

const active = computed(() => items.value.find((x) => x.type === activeKey.value) || null)

const activeDepends = computed(() => String(active.value?.depends || '').trim())

/** depends 指向的上级字典选项（供 parent 下拉 + 标题旁预览） */
const parentOptions = computed(() => {
  const dep = activeDepends.value
  if (!dep) return [] as DictItem[]
  const meta = bundle.value[dep]
  return (meta?.options || [])
    .map((o) => ({
      uukey: String(o.uukey || '').trim(),
      value: String(o.value || o.uukey || '').trim(),
      parent: String(o.parent || ''),
    }))
    .filter((o) => o.uukey)
})

const parentDictTitle = computed(() => {
  const dep = activeDepends.value
  if (!dep) return ''
  return String(bundle.value[dep]?.title || dep)
})

const filtered = computed(() => {
  const needle = q.value.trim().toLowerCase()
  const base = items.value.filter(
    (x) => !x.hidden && !String(x.type || '').endsWith('.status'),
  )
  if (!needle) return base
  return base.filter(
    (x) =>
      x.type.toLowerCase().includes(needle) ||
      (x.title || '').toLowerCase().includes(needle),
  )
})

async function load() {
  loading.value = true
  try {
    const merged: Record<string, DictMeta> = {}
    const src: Record<string, string> = {}
    for (const mod of props.mods) {
      const res = await fetch(
        `/api/base/config/item?mod=${encodeURIComponent(mod)}&type=${encodeURIComponent(CFG_TYPE)}`,
        { credentials: 'include' },
      )
      if (!res.ok) throw new Error(await res.text())
      const body = await res.json()
      const data = body.item?.data
      if (!data || typeof data !== 'object' || Array.isArray(data)) continue
      for (const [key, meta] of Object.entries(data as Record<string, DictMeta>)) {
        merged[key] = meta
        src[key] = mod
      }
    }
    bundle.value = merged
    sources.value = src
    if (!activeKey.value && filtered.value.length) {
      activeKey.value = filtered.value[0].type
    } else if (activeKey.value && !filtered.value.some((x) => x.type === activeKey.value)) {
      activeKey.value = filtered.value[0]?.type || ''
    }
  } catch (e) {
    appToast(e instanceof Error ? e.message : String(e), 'error')
  } finally {
    loading.value = false
  }
}

function selectType(type: string) {
  activeKey.value = type
}

function addRow() {
  draft.value = [...draft.value, { uukey: '', value: '', parent: '' }]
}

function removeRow(i: number) {
  draft.value = draft.value.filter((_, idx) => idx !== i)
}

async function save() {
  if (!activeKey.value) return
  saving.value = true
  try {
    const options = draft.value
      .map((r) => ({
        uukey: String(r.uukey || '').trim(),
        value: String(r.value || '').trim(),
        parent: activeDepends.value ? String(r.parent || '').trim() : '',
      }))
      .filter((r) => r.uukey)
    for (const r of options) {
      if (!r.value) r.value = r.uukey
    }
    const next = { ...bundle.value }
    const prev = next[activeKey.value] || {}
    next[activeKey.value] = {
      title: draftTitle.value || activeKey.value,
      depends: String(prev.depends || ''),
      hidden: Boolean(prev.hidden),
      options,
    }
    const nextSources = {
      ...sources.value,
      [activeKey.value]: sources.value[activeKey.value] || props.mods[props.mods.length - 1],
    }
    for (const mod of props.mods) {
      const data: Record<string, DictMeta> = {}
      for (const [key, meta] of Object.entries(next)) {
        if ((nextSources[key] || props.mods[0]) === mod) data[key] = meta
      }
      if (!Object.keys(data).length) continue
      const res = await fetch('/api/base/config', {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mod,
          type: CFG_TYPE,
          title: '字典设置',
          data,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
    }
    bundle.value = next
    sources.value = nextSources
    appToast('已保存')
  } catch (e) {
    appToast(e instanceof Error ? e.message : String(e), 'error')
  } finally {
    saving.value = false
  }
}

watch(
  active,
  (row) => {
    if (!row) {
      draft.value = []
      draftTitle.value = ''
      return
    }
    draftTitle.value = row.title || row.type
    draft.value = (row.data || []).map((d) => ({
      uukey: d.uukey || '',
      value: d.value || '',
      parent: d.parent || '',
    }))
  },
  { immediate: true },
)

onMounted(load)
</script>

<template>
  <div class="dict-panel">
    <!-- <p class="hint muted">全部 OPTIONAL 字典合在一行：mod=fleet · type=dict</p> -->
    <p v-if="loading" class="muted">加载中…</p>

    <div v-else class="sp-layout">
      <aside class="sp-side">
        <input v-model="q" class="sp-search" type="search" placeholder="筛选字典…" />
        <nav class="sp-nav" aria-label="dicts">
          <button
            v-for="it in filtered"
            :key="it.type"
            type="button"
            class="sp-nav-item"
            :class="{ active: it.type === activeKey }"
            @click="selectType(it.type)"
          >
            <span class="t">{{ it.title || it.type }}</span>
            <span class="k">{{ it.type }}</span>
          </button>
        </nav>
      </aside>

      <div class="sp-main" v-if="active">
        <div class="sp-main-head">
          <div class="head-fields">
            <div class="field">
              <label class="lbl">标题</label>
              <input v-model="draftTitle" class="inp" />
            </div>
            <div v-if="activeDepends" class="field field-depends">
              <label class="lbl">上级分类</label>
              <input
                class="inp"
                type="text"
                disabled
                readonly
                :value="parentDictTitle"
                :title="activeDepends"
              />
            </div>
          </div>
          <div class="actions">
            <button type="button" class="btn" @click="addRow">加一项</button>
            <button type="button" class="btn primary" :disabled="saving" @click="save">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </div>
        <!-- <p class="muted mono key-line">key={{ active.type }}</p> -->

        <div class="sp-table-wrap">
          <table class="sp-table">
            <thead>
              <tr>
                <th style="width: 28%">uukey</th>
                <th style="width: 36%">value</th>
                <th style="width: 28%">parent</th>
                <th style="width: 8%"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in draft" :key="i">
                <td><input v-model="row.uukey" class="inp" /></td>
                <td><input v-model="row.value" class="inp" /></td>
                <td>
                  <select
                    v-model="row.parent"
                    class="inp"
                    :disabled="!activeDepends"
                    :title="activeDepends ? '选择上级选项' : '无 depends，不可设 parent'"
                  >
                    <option value="">{{ activeDepends ? '（无）' : '—' }}</option>
                    <option v-for="opt in parentOptions" :key="opt.uukey" :value="opt.uukey">
                      {{ opt.value }} ({{ opt.uukey }})
                    </option>
                  </select>
                </td>
                <td>
                  <button type="button" class="btn danger" @click="removeRow(i)">删除</button>
                </td>
              </tr>
              <tr v-if="!draft.length">
                <td colspan="4" class="muted empty">暂无选项，点击「加一项」</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="sp-main muted">暂无字典</div>
    </div>
  </div>
</template>

<style scoped>
.dict-panel {
  padding: 12px 20px 16px;
  min-height: 0;
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
}
.hint {
  margin: 0 0 10px;
  flex-shrink: 0;
}
.muted {
  color: var(--muted, #6b6458);
  margin: 0;
  font-size: 13px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.key-line {
  margin: 8px 0 10px;
  flex-shrink: 0;
}
.sp-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}
.sp-side {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  padding: 10px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.sp-search {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  font: inherit;
  flex-shrink: 0;
}
.sp-nav {
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
}
.sp-nav-item {
  appearance: none;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font: inherit;
  width: 100%;
}
.sp-nav-item .t {
  font-weight: 600;
  color: var(--ink, #1c1914);
  min-width: 0;
  flex: 1;
}
.sp-nav-item .k {
  font-size: 11px;
  color: var(--muted, #6b6458);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
}
.sp-nav-item.active {
  background: #f3f1ec;
}
.sp-main {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  padding: 14px 16px;
  background: #fff;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sp-main-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.head-fields {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}
.field {
  min-width: 160px;
  flex: 1 1 180px;
  max-width: 280px;
}
.field-depends {
  max-width: 220px;
  flex: 0 1 220px;
}
.lbl {
  display: block;
  font-size: 12px;
  color: var(--muted, #6b6458);
  margin-bottom: 4px;
}
.inp {
  width: 100%;
  box-sizing: border-box;
  padding: 7px 9px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  font: inherit;
  background: #fff;
}
.inp:disabled {
  background: #f5f4f1;
  color: var(--muted, #6b6458);
  cursor: not-allowed;
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.btn {
  appearance: none;
  border: 1px solid var(--line, #e2e6eb);
  background: #fff;
  padding: 8px 12px;
  border-radius: 6px;
  font: inherit;
  cursor: pointer;
}
.btn.primary {
  background: var(--ink, #1c1914);
  color: #fff;
  border-color: var(--ink, #1c1914);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn.danger {
  color: #b42318;
  border-color: color-mix(in srgb, #b42318 35%, var(--line, #e2e6eb));
  padding: 5px 10px;
  font-size: 12px;
}
.btn.danger:hover {
  background: color-mix(in srgb, #b42318 8%, #fff);
}
.sp-table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.sp-table {
  width: 100%;
  border-collapse: collapse;
}
.sp-table th,
.sp-table td {
  border-bottom: 1px solid var(--line, #e2e6eb);
  padding: 6px 4px;
  text-align: left;
  font-size: 13px;
}
.sp-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fff;
  color: var(--muted, #6b6458);
  font-weight: 600;
  box-shadow: 0 1px 0 var(--line, #e2e6eb);
}
.empty {
  padding: 16px 4px !important;
}
@media (max-width: 900px) {
  .sp-layout {
    grid-template-columns: 1fr;
  }
}
</style>
