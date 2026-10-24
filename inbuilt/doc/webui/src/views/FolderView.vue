<template>
  <section class="folder-layout" @click="closeMenus">
    <p v-if="error" class="error list-error">{{ error }}</p>
    <main class="content">
      <!-- list -->
      <div v-if="viewMode === 'list'" class="view-body">
        <table class="file-table">
          <thead>
            <tr>
              <th>{{ t('doc.colName') }}</th>
              <th>{{ t('doc.colType') }}</th>
              <th>{{ t('doc.colSize') }}</th>
              <th class="col-time">{{ t('doc.colUpdated') }}</th>
              <th class="col-more"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="a in items"
              :key="a.id"
              class="file-row"
              @click="openFile(a.id)"
              @dblclick="openFile(a.id)"
            >
              <td>
                <span class="type-badge">{{ typeLabel(a) }}</span>
                <span class="file-title">{{ a.title }}</span>
                <span v-if="extractChip(a)" class="extract-chip" :class="a.text_status">{{ extractChip(a) }}</span>
                <span class="muted file-sub">{{ a.filename }}</span>
              </td>
              <td class="muted mono">{{ extOf(a) || '—' }}</td>
              <td class="muted">{{ formatSize(a.size_bytes) }}</td>
              <td class="muted col-time">{{ formatTime(a.updated_at) }}</td>
              <td class="col-more" @click.stop>
                <div class="more-wrap" :class="{ open: openMenuId === a.id }">
                  <button
                    type="button"
                    class="more-btn"
                    :aria-label="t('doc.more')"
                    :aria-expanded="openMenuId === a.id"
                    @click.stop="toggleMenu($event, a.id)"
                  >⋯</button>
                </div>
              </td>
            </tr>
            <tr v-if="!items.length">
              <td colspan="5" class="empty muted">{{ t('doc.empty') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- icon -->
      <div v-else-if="viewMode === 'icon'" class="view-body icon-grid">
        <button
          v-for="a in items"
          :key="a.id"
          type="button"
          class="icon-tile"
          @click="openFile(a.id)"
        >
          <span class="icon-glyph">{{ typeLabel(a) }}</span>
          <span class="icon-title">{{ a.title }}</span>
          <span v-if="extractChip(a)" class="extract-chip" :class="a.text_status">{{ extractChip(a) }}</span>
          <span class="muted icon-sub">{{ extOf(a) || 'file' }} · {{ formatSize(a.size_bytes) }}</span>
        </button>
        <p v-if="!items.length" class="empty muted">{{ t('doc.empty') }}</p>
      </div>

      <!-- split -->
      <div v-else class="view-body split-view">
        <ul class="split-list">
          <li
            v-for="a in items"
            :key="a.id"
            class="split-item"
            :class="{ active: focusId === a.id }"
            @click="focusId = a.id"
            @dblclick="openFile(a.id)"
          >
            <div class="split-item-main">
              <strong>{{ a.title }}</strong>
              <span class="muted">{{ typeLabel(a) }} · {{ formatSize(a.size_bytes) }}</span>
              <span v-if="extractChip(a)" class="extract-chip" :class="a.text_status">{{ extractChip(a) }}</span>
            </div>
            <div class="split-item-more" @click.stop>
              <div class="more-wrap" :class="{ open: openMenuId === a.id }">
                <button
                  type="button"
                  class="more-btn"
                  :aria-label="t('doc.more')"
                  :aria-expanded="openMenuId === a.id"
                  @click.stop="toggleMenu($event, a.id)"
                >⋯</button>
              </div>
            </div>
          </li>
          <li v-if="!items.length" class="muted empty">{{ t('doc.empty') }}</li>
        </ul>
        <div class="split-preview">
          <PreviewPane v-if="focusAsset" :asset="focusAsset" @updated="onAssetUpdated" />
          <p v-else class="empty muted">{{ t('doc.pickPreview') }}</p>
        </div>
      </div>
    </main>

    <div
      v-if="infoAsset"
      class="dialog-backdrop"
      role="presentation"
      @click.self="infoAsset = null"
    >
      <div class="info-dialog" role="dialog" aria-modal="true" :aria-label="t('doc.infoTitle')" @click.stop>
        <header class="info-dialog-head">
          <h2>{{ t('doc.infoTitle') }}</h2>
          <button type="button" class="dialog-close" :aria-label="t('doc.close')" @click="infoAsset = null">×</button>
        </header>
        <dl class="info-dl">
          <div>
            <dt>{{ t('doc.colName') }}</dt>
            <dd>{{ infoAsset.title }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colFilename') }}</dt>
            <dd>{{ infoAsset.filename }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colType') }}</dt>
            <dd>{{ typeLabel(infoAsset) }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colSize') }}</dt>
            <dd>{{ formatSize(infoAsset.size_bytes) }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colUpdated') }}</dt>
            <dd>{{ formatTime(infoAsset.updated_at) }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colMime') }}</dt>
            <dd>{{ infoAsset.mime_type || '—' }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colTags') }}</dt>
            <dd>{{ infoAsset.tags?.length ? infoAsset.tags.join(' · ') : '—' }}</dd>
          </div>
          <div v-if="originText(infoAsset)">
            <dt>{{ t('doc.colOrigin') }}</dt>
            <dd>{{ originText(infoAsset) }}</dd>
          </div>
          <div>
            <dt>{{ t('doc.colExtract') }}</dt>
            <dd>
              {{ extractInfo(infoAsset) }}
              <span v-if="infoAsset.text_method" class="muted"> · {{ infoAsset.text_method }}</span>
            </dd>
          </div>
          <div v-if="infoAsset.text_error">
            <dt>{{ t('doc.extractFailed') }}</dt>
            <dd>{{ infoAsset.text_error }}</dd>
          </div>
          <div v-if="infoAsset.note">
            <dt>{{ t('doc.colNote') }}</dt>
            <dd>{{ infoAsset.note }}</dd>
          </div>
        </dl>
      </div>
    </div>
    <Teleport to="body">
      <div
        v-if="menuAsset"
        class="doc-more-menu"
        role="menu"
        :style="menuStyle"
        @click.stop
      >
        <button type="button" role="menuitem" @click="openFile(menuAsset.id)">{{ t('doc.view') }}</button>
        <button type="button" role="menuitem" @click="openInfo(menuAsset)">{{ t('doc.info') }}</button>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { registerShellSearch, useI18n } from '@modoor/hooks'
import { getAsset, listAssets, type DocAsset } from '../api/doc'
import PreviewPane from '../components/PreviewPane.vue'
import { docFilter, docQuery, libraryEpoch, modelLabel, viewMode } from './library'

const router = useRouter()
const { t } = useI18n()
const error = ref('')
const items = ref<DocAsset[]>([])
const focusId = ref<string | null>(null)
const focusAsset = ref<DocAsset | null>(null)
const openMenuId = ref<string | null>(null)
const menuStyle = ref<Record<string, string>>({})
const infoAsset = ref<DocAsset | null>(null)
const focusStillExists = computed(() =>
  focusId.value ? items.value.some((a) => a.id === focusId.value) : false,
)

function formatSize(n: number) {
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(raw?: string | null) {
  if (!raw) return '—'
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function extOf(a: DocAsset) {
  return (a.ext || a.filename.split('.').pop() || '').toLowerCase()
}

function extractChip(a: DocAsset) {
  if (a.text_status === 'pending' || a.text_status === 'running') return t('doc.extracting')
  if (a.text_status === 'failed') return t('doc.extractFailed')
  return ''
}

function extractInfo(a: DocAsset) {
  if (a.text_status === 'pending' || a.text_status === 'running') return t('doc.extracting')
  if (a.text_status === 'failed') return t('doc.extractFailed')
  return t('doc.extractReady')
}

function originText(a: DocAsset) {
  return [a.model ? modelLabel(a.model) : '', a.uukey, a.field].filter(Boolean).join(' · ')
}

function typeLabel(a: DocAsset) {
  const e = extOf(a)
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(e)) return t('doc.typeImage')
  if (e === 'pdf') return t('doc.typePdf')
  if (['txt', 'md', 'csv', 'json', 'log'].includes(e)) return t('doc.typeText')
  if (e === 'xlsx' || e === 'xls') return t('doc.typeExcel')
  if (e === 'docx' || e === 'doc') return t('doc.typeWord')
  if (e === 'pptx' || e === 'ppt') return t('doc.typePpt')
  return e ? e.toUpperCase() : t('doc.typeFile')
}

function openFile(id: string) {
  closeMenus()
  void router.push(`/mod/doc/${encodeURIComponent(id)}`)
}

const menuAsset = computed(() =>
  openMenuId.value ? items.value.find((a) => a.id === openMenuId.value) || null : null,
)

function toggleMenu(ev: MouseEvent, id: string) {
  ev.stopPropagation()
  if (openMenuId.value === id) {
    closeMenus()
    return
  }
  openMenuId.value = id
  const r = (ev.currentTarget as HTMLElement).getBoundingClientRect()
  const width = 120
  menuStyle.value = {
    position: 'fixed',
    top: `${r.bottom + 4}px`,
    left: `${Math.min(Math.max(8, r.right - width), window.innerWidth - width - 8)}px`,
    zIndex: '80',
  }
}

function closeMenus() {
  openMenuId.value = null
}

function onMenuPointer(e: Event) {
  const el = e.target as HTMLElement | null
  if (el?.closest?.('.more-btn, .doc-more-menu')) return
  closeMenus()
}

function openInfo(a: DocAsset) {
  closeMenus()
  infoAsset.value = a
}

async function reload() {
  error.value = ''
  try {
    const filter = docFilter.value
    const assetsRes = await listAssets({
      q: docQuery.value.trim() || undefined,
      tag: filter.kind === 'tag' ? filter.tag : undefined,
      model: filter.kind === 'model' ? filter.model : undefined,
      tagEmpty: filter.kind === 'tag-empty',
      modelEmpty: filter.kind === 'model-empty',
      limit: 200,
    })
    items.value = assetsRes.items || []
    if (infoAsset.value) {
      const next = items.value.find((a) => a.id === infoAsset.value?.id)
      if (next) infoAsset.value = { ...infoAsset.value, ...next }
    }
    if (focusId.value && !focusStillExists.value) {
      focusId.value = items.value[0]?.id ?? null
    } else if (viewMode.value === 'split' && !focusId.value && items.value[0]) {
      focusId.value = items.value[0].id
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function onAssetUpdated(asset: DocAsset) {
  if (focusAsset.value?.id === asset.id) focusAsset.value = asset
  const index = items.value.findIndex((item) => item.id === asset.id)
  if (index >= 0) items.value[index] = { ...items.value[index], ...asset }
  if (infoAsset.value?.id === asset.id) infoAsset.value = { ...infoAsset.value, ...asset }
}

async function loadFocus() {
  if (!focusId.value || viewMode.value !== 'split') {
    focusAsset.value = null
    return
  }
  try {
    const res = await getAsset(focusId.value)
    focusAsset.value = res.asset
  } catch (e) {
    focusAsset.value = null
    error.value = e instanceof Error ? e.message : String(e)
  }
}

watch(focusId, () => {
  void loadFocus()
})
watch(viewMode, (v) => {
  closeMenus()
  if (v === 'split' && !focusId.value && items.value[0]) {
    focusId.value = items.value[0].id
  }
  void loadFocus()
})

watch([docFilter, docQuery, libraryEpoch], () => {
  void reload()
})

let unregisterSearch: (() => void) | null = null
let extractTimer: ReturnType<typeof setInterval> | null = null

function extracting(a: DocAsset) {
  return a.text_status === 'pending' || a.text_status === 'running'
}

function syncExtractPoll() {
  const busy = items.value.some(extracting) || (focusAsset.value ? extracting(focusAsset.value) : false)
  if (busy && extractTimer == null) {
    extractTimer = setInterval(() => {
      void reload()
      void loadFocus()
    }, 1500)
  }
  if (!busy && extractTimer != null) {
    clearInterval(extractTimer)
    extractTimer = null
  }
}

watch(items, syncExtractPoll, { deep: true })
watch(focusAsset, syncExtractPoll)

onMounted(() => {
  void reload()
  unregisterSearch = registerShellSearch('doc.folder', (query) => {
    docQuery.value = query
    void reload()
  })
  window.addEventListener('keydown', onKeydown)
  document.addEventListener('mousedown', onMenuPointer)
})

onUnmounted(() => {
  unregisterSearch?.()
  unregisterSearch = null
  if (extractTimer != null) {
    clearInterval(extractTimer)
    extractTimer = null
  }
  window.removeEventListener('keydown', onKeydown)
  document.removeEventListener('mousedown', onMenuPointer)
})

function onKeydown(ev: KeyboardEvent) {
  if (ev.key !== 'Escape') return
  if (infoAsset.value) {
    infoAsset.value = null
    return
  }
  closeMenus()
}
</script>

<style scoped>
.folder-layout {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-error {
  margin: 8px 12px 0;
}

.content {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.view-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

.file-table th {
  text-align: left;
  font-size: 0.75rem;
  color: var(--muted);
  font-weight: 600;
  border-bottom: 1px solid var(--line);
  padding: 8px 12px;
  position: sticky;
  top: 0;
  background: var(--bg, #f5f7f9);
}

.file-row {
  cursor: pointer;
}

.file-row:hover {
  background: #eef1f4;
}

.file-row td {
  padding: 9px 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 65%, transparent);
  vertical-align: middle;
}

.col-time {
  white-space: nowrap;
  width: 1%;
}

.type-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: #0000000a;
  margin-right: 8px;
}

.file-title {
  font-weight: 600;
}

.extract-chip {
  display: inline-block;
  margin-left: 8px;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: var(--radius-pill);
  vertical-align: middle;
}

.extract-chip.pending,
.extract-chip.running {
  color: #9a5b12;
  background: #f5e0c4;
}

.extract-chip.failed {
  color: #8b1e1e;
  background: #f3d2d2;
}

.file-sub {
  margin-left: 8px;
  font-size: 0.78rem;
}

.mono {
  text-transform: uppercase;
  font-size: 0.78rem;
}

.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  align-content: start;
  padding: 12px;
}

.icon-tile {
  display: grid;
  justify-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  padding: 12px 8px;
  border-radius: var(--radius-lg);
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
}

.icon-tile:hover {
  background: #eef1f4;
}

.icon-glyph {
  display: grid;
  place-items: center;
  width: 56px;
  height: 64px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: #fff;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.icon-title {
  font-size: 0.85rem;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-sub {
  font-size: 0.72rem;
}

.split-view {
  display: grid;
  grid-template-columns: minmax(200px, 280px) 1fr;
  gap: 0;
  overflow: hidden;
  isolation: isolate;
}

.split-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  border-right: 1px solid var(--line);
  position: relative;
  z-index: 2;
}

.col-more {
  width: 2.5rem;
  text-align: right;
}

.more-wrap.open {
  z-index: 22;
}

.more-btn {
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 1.1rem;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius-md);
}

.more-btn:hover,
.more-wrap.open .more-btn {
  background: #0000000d;
  color: var(--ink);
}

.split-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 8px 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent);
}

.split-item-main {
  display: grid;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.split-item-more {
  flex-shrink: 0;
}

.split-item:hover {
  background: #eef1f4;
}

.split-item.active {
  background: #eef6f3;
}

.split-item strong {
  font-size: 0.92rem;
}

.split-item .muted {
  font-size: 0.78rem;
}

.split-preview {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.split-preview :deep(.preview-wrap) {
  flex: 1;
  min-height: 0;
  padding: 12px;
}

.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  background: rgba(28, 25, 23, 0.28);
  padding: 1.5rem;
}

.info-dialog {
  width: min(100%, 26rem);
  background: var(--panel, #ffffff);
  border: 1px solid var(--line);
  border-radius: var(--radius-xl);
  box-shadow: 0 18px 48px rgba(28, 25, 23, 0.14);
  padding: 1.1rem 1.2rem 1.25rem;
}

.info-dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 0.85rem;
}

.info-dialog-head h2 {
  margin: 0;
  font-size: 1.05rem;
}

.dialog-close {
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 1.35rem;
  line-height: 1;
  color: var(--muted);
  cursor: pointer;
  padding: 0 4px;
}

.dialog-close:hover {
  color: var(--ink);
}

.info-dl {
  margin: 0;
  display: grid;
  gap: 0.7rem;
}

.info-dl div {
  display: grid;
  gap: 0.15rem;
}

.info-dl dt {
  font-size: 0.75rem;
  color: var(--muted);
}

.info-dl dd {
  margin: 0;
  font-size: 0.92rem;
  word-break: break-word;
}

.empty {
  padding: 28px 8px;
  text-align: center;
}

@media (max-width: 860px) {
  .folder-layout {
    grid-template-columns: 1fr;
  }
  .sidebar {
    border-right: 0;
    border-bottom: 1px solid var(--line);
    max-height: 280px;
  }
  .split-view {
    grid-template-columns: 1fr;
  }
  .split-list {
    max-height: 180px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
}
</style>

<style>
.doc-more-menu {
  min-width: 7.5rem;
  background: var(--panel, #ffffff);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: 0 10px 24px rgba(28, 25, 23, 0.1);
  padding: 4px;
}

.doc-more-menu button {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  font: inherit;
  font-size: 0.88rem;
  cursor: pointer;
  color: inherit;
}

.doc-more-menu button:hover {
  background: #eef6f3;
  color: var(--accent);
}
</style>
