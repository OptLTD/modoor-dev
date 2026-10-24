<template>
  <section class="skill-layout">
    <aside class="sidebar">
      <div class="side-head">
        <h1>{{ t('skill.title') }}</h1>
        <button class="btn primary" type="button" @click="startNew">
          {{ t('skill.newCustom') }}
        </button>
      </div>
      <input
        v-model="q"
        class="filter-input"
        :placeholder="t('skill.searchPh')"
        @keyup.enter="reload"
      />
      <p v-if="listError" class="error side-error">{{ listError }}</p>
      <nav class="tree">
        <div v-for="group in groups" :key="group.module" class="tree-group">
          <button
            type="button"
            class="tree-group-head"
            :aria-expanded="!collapsed[group.module]"
            @click="toggleGroup(group.module)"
          >
            <span class="chevron" aria-hidden="true">{{ collapsed[group.module] ? '▸' : '▾' }}</span>
            <span class="group-name">{{ group.module }}</span>
            <span class="muted group-count">{{ group.items.length }}</span>
          </button>
          <ul v-show="!collapsed[group.module]">
            <li v-for="s in group.items" :key="s.id">
              <button
                type="button"
                class="tree-item"
                :class="{ active: activeId === s.id }"
                @click="selectSkill(s.id)"
              >
                <span class="tree-title">{{ s.title }}</span>
                <span v-if="s.disabled" class="badge muted">{{ t('skill.disabled') }}</span>
                <span v-else-if="s.readonly" class="badge muted">{{ t('skill.readonly') }}</span>
                <span v-else-if="s.overridden" class="badge">{{ t('skill.overridden') }}</span>
              </button>
            </li>
          </ul>
        </div>
        <p v-if="!groups.length" class="muted empty">{{ t('skill.empty') }}</p>
      </nav>
    </aside>

    <main class="content">
      <p v-if="error" class="error content-error">{{ error }}</p>

      <div v-if="creating || skill" class="editor-pane">
        <header class="pane-head">
          <div class="pane-head-main">
            <h2>{{ creating ? t('skill.newCustom') : skill?.title }}</h2>
            <p v-if="!creating && skill" class="muted meta-line">
              <code>{{ skill.id }}</code>
              · {{ skill.module }}
              <template v-if="skill.disabled"> · {{ t('skill.disabled') }}</template>
              <template v-if="skill.overridden"> · {{ t('skill.overridden') }}</template>
              <template v-if="skill.readonly"> · {{ t('skill.readonly') }}</template>
              <template v-if="saveHint"> · {{ saveHint }}</template>
              <template v-else-if="skill.updated_at"> · {{ skill.updated_at }}</template>
            </p>
            <p v-else-if="creating" class="muted meta-line">
              {{ t('skill.customOnlyHint') }}
              <template v-if="saveHint"> · {{ saveHint }}</template>
            </p>
          </div>
          <div class="row-actions">
            <template v-if="creating">
              <button class="btn" type="button" @click="openMeta">
                {{ t('skill.edit') }}
              </button>
              <button class="btn" type="button" @click="cancelCreate">
                {{ t('skill.cancel') }}
              </button>
            </template>
            <template v-else-if="skill">
              <div class="action-stack">
                <button
                  v-if="canEdit"
                  class="btn"
                  type="button"
                  @click="openMeta"
                >
                  {{ t('skill.edit') }}
                </button>
                <Dropdown wide align="end" :label="t('skill.more')">
                  <button type="button" class="dropdown-item" role="menuitem" @click="onToggleDisabled">
                    {{ skill.disabled ? t('skill.enable') : t('skill.disable') }}
                  </button>
                  <button
                    v-if="canDelete"
                    type="button"
                    class="dropdown-item danger"
                    role="menuitem"
                    @click="onDeleteCustom"
                  >
                    {{ t('skill.delete') }}
                  </button>
                </Dropdown>
              </div>
            </template>
          </div>
        </header>

        <!-- <p v-if="skill?.readonly" class="notice muted">{{ t('skill.baseReadonlyNotice') }}</p> -->

        <div class="body-wrap" :class="{ 'is-readonly': !canEdit }">
          <MdEditor
            :key="editorKey"
            v-model="form.content"
            :language="mdLang"
            :toolbars="toolbars"
            :preview="false"
            :preview-only="!canEdit"
            :html-preview="false"
            :read-only="!canEdit"
            preview-theme="default"
            class="body-editor"
          />
        </div>
      </div>

      <div v-else class="empty-pane muted">
        {{ t('skill.pickHint') }}
      </div>
    </main>

    <div v-if="metaOpen" class="modal-mask" @click.self="metaOpen = false">
      <div class="modal meta-modal" role="dialog" aria-modal="true">
        <header class="modal-head">
          <strong>{{ t('skill.metaTitle') }}</strong>
          <button class="btn" type="button" @click="metaOpen = false">{{ t('skill.close') }}</button>
        </header>
        <form class="form" @submit.prevent="applyMeta">
          <label v-if="creating">
            Skill key
            <input v-model="form.skill_key" required pattern="[a-z][a-z0-9_]*" />
          </label>
          <label>
            Title
            <input v-model="form.title" required />
          </label>
          <label>
            Summary
            <textarea v-model="form.summary" rows="2" />
          </label>
          <label>
            {{ t('skill.whenToUse') }}
            <textarea v-model="form.when_to_use" rows="3" />
          </label>
          <label>
            {{ t('skill.toolsLabel') }}
            <input v-model="toolsText" placeholder="fleet.query, fleet.read" />
          </label>
          <label>
            {{ t('skill.boundariesLabel') }}
            <textarea v-model="form.boundaries" rows="2" />
          </label>
          <div class="modal-actions">
            <button class="btn" type="button" @click="metaOpen = false">{{ t('skill.cancel') }}</button>
            <button class="btn primary" type="submit" :disabled="saving">
              {{ t('skill.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import 'md-editor-v3/lib/style.css'
import { MdEditor, type ToolbarNames } from 'md-editor-v3'
import { registerShellSearch, useI18n } from '@modoor/hooks'
import { Dropdown } from '@modoor/widget'
import {
  deleteSkill,
  getSkill,
  listSkills,
  saveSkill,
  setSkillDisabled,
  type SkillItem,
} from '../api/skill'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const skills = ref<SkillItem[]>([])
const skill = ref<SkillItem | null>(null)
const listError = ref('')
const error = ref('')
const q = ref('')
const saving = ref(false)
const creating = ref(false)
const metaOpen = ref(false)
const hydrateLock = ref(false)
const saveStatus = ref<'idle' | 'dirty' | 'saving' | 'saved' | 'error'>('idle')
const collapsed = reactive<Record<string, boolean>>({})
const toolsText = ref('')
const form = reactive({
  skill_key: '',
  title: '',
  summary: '',
  when_to_use: '',
  content: '',
  boundaries: '',
})

const mdLang = computed(() => (String(locale.value || '').startsWith('zh') ? 'zh-CN' : 'en-US'))
const activeId = computed(() => {
  if (creating.value) return ''
  return decodeURIComponent(String(route.params.id || ''))
})
const canEdit = computed(() => creating.value || Boolean(skill.value && !skill.value.readonly))
/** Only pure custom.* skills can be deleted; module-synced ones can only be disabled. */
const canDelete = computed(
  () => Boolean(skill.value && skill.value.module === 'custom' && !creating.value),
)
const editorKey = computed(
  () => `${creating.value ? 'new' : activeId.value || 'none'}:${canEdit.value ? 'edit' : 'view'}`,
)
const saveHint = computed(() => {
  if (saveStatus.value === 'saving') return t('skill.saving')
  if (saveStatus.value === 'saved') return t('skill.saved')
  if (saveStatus.value === 'dirty') return t('skill.dirty')
  if (saveStatus.value === 'error') return t('skill.saveFailed')
  return ''
})

const groups = computed(() => {
  const map = new Map<string, SkillItem[]>()
  for (const s of skills.value) {
    const m = s.module || 'custom'
    if (!map.has(m)) map.set(m, [])
    map.get(m)!.push(s)
  }
  return [...map.entries()]
    .sort(([a], [b]) => {
      if (a === 'base') return -1
      if (b === 'base') return 1
      if (a === 'custom') return 1
      if (b === 'custom') return -1
      return a.localeCompare(b)
    })
    .map(([module, items]) => ({ module, items }))
})

const toolbars: ToolbarNames[] = [
  'bold',
  'underline',
  'italic',
  '-',
  'title',
  'strikeThrough',
  'quote',
  'unorderedList',
  'orderedList',
  'task',
  '-',
  'codeRow',
  'code',
  'link',
  'table',
  '-',
  'revoke',
  'next',
  '=',
  'preview',
  'previewOnly',
  'fullscreen',
]

let saveTimer: ReturnType<typeof setTimeout> | null = null
let saveSeq = 0
let lastSavedContent = ''

function parseTools(raw: string): string[] {
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function toggleGroup(module: string) {
  collapsed[module] = !collapsed[module]
}

function clearSaveTimer() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
}

function fillForm(s: SkillItem) {
  hydrateLock.value = true
  form.skill_key = s.skill_key
  form.title = s.title
  form.summary = s.summary || ''
  form.when_to_use = s.when_to_use || ''
  form.content = s.content || s.markdown || ''
  form.boundaries = s.boundaries || ''
  toolsText.value = (s.tools || []).map(String).join(', ')
  lastSavedContent = form.content
  saveStatus.value = 'idle'
  queueMicrotask(() => {
    hydrateLock.value = false
  })
}

function openMeta() {
  metaOpen.value = true
}

async function onToggleDisabled() {
  if (!skill.value) return
  const next = !skill.value.disabled
  const msg = next
    ? t('skill.confirmDisable', { id: skill.value.id })
    : t('skill.confirmEnable', { id: skill.value.id })
  if (!confirm(msg)) return
  try {
    const res = await setSkillDisabled(skill.value.id, next)
    skill.value = res.skill
    await reload()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onDeleteCustom() {
  if (!skill.value || !canDelete.value) return
  const msg = t('skill.confirmDelete', { id: skill.value.id })
  if (!confirm(msg)) return
  clearSaveTimer()
  try {
    await deleteSkill(skill.value.id)
    await reload()
    const next = skills.value[0]
    if (next) selectSkill(next.id)
    else {
      skill.value = null
      router.push('/mod/skill')
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function scheduleAutoSave() {
  if (hydrateLock.value || !canEdit.value) return
  if (creating.value && (!form.skill_key.trim() || !form.title.trim())) return
  if (form.content === lastSavedContent) return
  saveStatus.value = 'dirty'
  clearSaveTimer()
  saveTimer = setTimeout(() => {
    void persist()
  }, 800)
}

async function persist(opts?: { closeMeta?: boolean }) {
  if (!canEdit.value) return
  if (creating.value && (!form.skill_key.trim() || !form.title.trim())) {
    metaOpen.value = true
    error.value = t('skill.metaRequired')
    return
  }
  if (!form.title.trim()) {
    metaOpen.value = true
    error.value = t('skill.metaRequired')
    return
  }

  clearSaveTimer()
  const seq = ++saveSeq
  saving.value = true
  saveStatus.value = 'saving'
  error.value = ''
  try {
    const res = await saveSkill({
      skill_id: creating.value ? undefined : skill.value?.id,
      module: creating.value ? 'custom' : skill.value?.module,
      skill_key: creating.value ? form.skill_key : skill.value?.skill_key,
      record_id: creating.value ? undefined : skill.value?.record_id,
      title: form.title,
      summary: form.summary,
      when_to_use: form.when_to_use,
      content: form.content,
      boundaries: form.boundaries,
      tools: parseTools(toolsText.value),
    })
    if (seq !== saveSeq) return

    const wasCreating = creating.value
    creating.value = false
    lastSavedContent = form.content
    saveStatus.value = 'saved'
    if (opts?.closeMeta) metaOpen.value = false

    await reload()
    if (wasCreating || skill.value?.id !== res.skill.id) {
      await router.push(`/mod/skill/${encodeURIComponent(res.skill.id)}`)
    }
    skill.value = res.skill
    // Keep local content; only sync meta fields that may change on server.
    hydrateLock.value = true
    form.title = res.skill.title
    form.summary = res.skill.summary || ''
    form.when_to_use = res.skill.when_to_use || ''
    form.boundaries = res.skill.boundaries || ''
    form.skill_key = res.skill.skill_key
    toolsText.value = (res.skill.tools || []).map(String).join(', ')
    queueMicrotask(() => {
      hydrateLock.value = false
    })
  } catch (e) {
    if (seq !== saveSeq) return
    saveStatus.value = 'error'
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (seq === saveSeq) saving.value = false
  }
}

async function applyMeta() {
  await persist({ closeMeta: true })
}

async function reload() {
  listError.value = ''
  try {
    const res = await listSkills({ q: q.value.trim() || undefined })
    skills.value = res.items || []
  } catch (e) {
    listError.value = e instanceof Error ? e.message : String(e)
  }
}

async function loadActive() {
  error.value = ''
  clearSaveTimer()
  creating.value = false
  metaOpen.value = false
  saveStatus.value = 'idle'
  const id = activeId.value
  if (!id) {
    skill.value = null
    return
  }
  try {
    const res = await getSkill(id)
    skill.value = res.skill
    fillForm(res.skill)
  } catch (e) {
    skill.value = null
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function selectSkill(id: string) {
  if (creating.value) {
    creating.value = false
    metaOpen.value = false
  }
  clearSaveTimer()
  if (id === activeId.value) return
  router.push(`/mod/skill/${encodeURIComponent(id)}`)
}

function startNew() {
  clearSaveTimer()
  creating.value = true
  skill.value = null
  hydrateLock.value = true
  form.skill_key = ''
  form.title = ''
  form.summary = ''
  form.when_to_use = ''
  form.content = ''
  form.boundaries = ''
  toolsText.value = ''
  lastSavedContent = ''
  saveStatus.value = 'idle'
  metaOpen.value = true
  router.push('/mod/skill')
  queueMicrotask(() => {
    hydrateLock.value = false
  })
}

function cancelCreate() {
  clearSaveTimer()
  creating.value = false
  metaOpen.value = false
  if (skills.value[0]) selectSkill(skills.value[0].id)
  else {
    skill.value = null
    router.push('/mod/skill')
  }
}

watch(
  () => form.content,
  () => {
    scheduleAutoSave()
  },
)

watch(
  () => route.params.id,
  () => {
    void loadActive()
  },
)

let unregisterSearch: (() => void) | null = null

onMounted(async () => {
  await reload()
  if (!route.params.id && skills.value.length) {
    await router.replace(`/mod/skill/${encodeURIComponent(skills.value[0].id)}`)
  } else {
    await loadActive()
  }
  unregisterSearch = registerShellSearch('skill.catalog', (query) => {
    q.value = query
    void reload()
  })
})

onUnmounted(() => {
  clearSaveTimer()
  unregisterSearch?.()
})
</script>

<style scoped>
.skill-layout {
  gap: 0;
  display: grid;
  margin: -16px -1rem;
  min-height: calc(100vh - 4.5rem);
  grid-template-columns: 260px 1fr;
  /* background: var(--panel, #fff); */
}
.sidebar {
  border-right: 1px solid var(--border, #e5e7eb);
  padding: 1rem 0.75rem;
  background: var(--surface-2, #f7f7f5);
  overflow: auto;
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.side-head h1 {
  font-size: 1.1rem;
  margin: 0;
}
.filter-input {
  width: 100%;
  margin-bottom: 0.75rem;
  box-sizing: border-box;
}
.tree-group {
  margin-bottom: 0.35rem;
}
.tree-group-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: transparent;
  border: 0;
  padding: 0.4rem 0.35rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  border-radius: 6px;
}
.tree-group-head:hover {
  background: rgba(0, 0, 0, 0.04);
}
.chevron {
  width: 1rem;
  color: #888;
  font-size: 0.85em;
}
.group-name {
  flex: 1;
}
.group-count {
  font-weight: 500;
  font-size: 0.85em;
}
.tree ul {
  list-style: none;
  margin: 0;
  padding: 0 0 0 1.1rem;
}
.tree-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  border: 0;
  background: transparent;
  padding: 0.35rem 0.45rem;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}
.tree-item:hover,
.tree-item.active {
  background: #e8f0fe;
}
.tree-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  display: inline-block;
  padding: 0.05rem 0.35rem;
  border-radius: 4px;
  background: #e8f0fe;
  font-size: 0.75em;
}
.badge.muted {
  background: #eee;
}
.content {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: auto;
  /* background: #fff; */
}
.content-error {
  margin: 0.75rem 1.25rem 0;
}
.editor-pane {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
.pane-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1.25rem;
  background: #fff;
  border-bottom: 1px solid var(--border, #e5e7eb);
  position: sticky;
  top: 0;
  z-index: 2;
}
.pane-head h2 {
  margin: 0 0 0.2rem;
  font-size: 1.25rem;
}
.row-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.4rem;
}
.action-stack {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.4rem;
  min-width: 5.5rem;
}
.action-stack > .btn {
  width: 100%;
  justify-content: center;
}
.meta-line {
  margin: 0;
  font-size: 0.9rem;
}
.notice {
  margin: 0;
  padding: 0.75rem 1.25rem 0;
}
.body-wrap {
  flex: 1;
  padding: 1rem 1.25rem 1.5rem;
  min-height: 0;
}
.body-editor {
  height: calc(100vh - 11rem);
  border-radius: 8px;
  overflow: hidden;
}
.body-wrap.is-readonly .body-editor :deep(.md-editor-toolbar-wrapper) {
  display: none;
}
.body-wrap.is-readonly .body-editor :deep(.md-editor-preview-wrapper) {
  padding: 1.25rem 1.5rem 2rem;
}
.body-wrap.is-readonly .body-editor :deep(.md-editor-preview) {
  max-width: 52rem;
}
.empty-pane {
  padding: 3rem 1.25rem;
}
.side-error,
.empty {
  padding: 0.5rem;
}
.meta-modal {
  width: min(560px, 100%);
}
@media (max-width: 860px) {
  .skill-layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    max-height: 40vh;
    border-right: 0;
    border-bottom: 1px solid var(--border, #e5e7eb);
  }
  .body-editor {
    height: 28rem;
  }
}
</style>
