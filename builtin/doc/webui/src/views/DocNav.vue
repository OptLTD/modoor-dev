<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from '@modoor/hooks'
import { docQuery, uploadDocFiles, uploading, viewMode, type ViewMode } from './library'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const input = ref<HTMLInputElement | null>(null)
const draft = ref(docQuery.value)
let queryTimer: ReturnType<typeof setTimeout> | null = null

function ensureFolder() {
  if (route.name === 'doc.preview') void router.push({ name: 'doc.folder' })
}

watch(draft, (value) => {
  if (queryTimer) clearTimeout(queryTimer)
  queryTimer = setTimeout(() => {
    docQuery.value = value.trim()
    if (value.trim()) ensureFolder()
  }, 200)
})

onUnmounted(() => {
  if (queryTimer) clearTimeout(queryTimer)
})

const modes: { id: ViewMode; label: string }[] = [
  { id: 'list', label: t('doc.viewList') },
  { id: 'icon', label: t('doc.viewIcon') },
  { id: 'split', label: t('doc.viewSplit') },
]

async function onPick(ev: Event) {
  const target = ev.target as HTMLInputElement
  const files = Array.from(target.files || [])
  target.value = ''
  const lastId = await uploadDocFiles(files)
  if (lastId) void router.push(`/mod/doc/${encodeURIComponent(lastId)}`)
}
</script>

<template>
  <div class="doc-nav">
    <div class="doc-modes" role="group" :aria-label="t('doc.library')">
      <button
        v-for="mode in modes"
        :key="mode.id"
        type="button"
        class="doc-nav-btn"
        :class="{ active: viewMode === mode.id }"
        :title="mode.label"
        :aria-label="mode.label"
        :aria-pressed="viewMode === mode.id"
        @click="viewMode = mode.id"
      >
        <svg v-if="mode.id === 'list'" class="doc-nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 7h12M8 12h12M8 17h12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
          <circle cx="4.5" cy="7" r="1" fill="currentColor" />
          <circle cx="4.5" cy="12" r="1" fill="currentColor" />
          <circle cx="4.5" cy="17" r="1" fill="currentColor" />
        </svg>
        <svg v-else-if="mode.id === 'icon'" class="doc-nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="4" y="4" width="6.5" height="6.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
        </svg>
        <svg v-else class="doc-nav-icon" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="5" width="7" height="14" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
          <rect x="12.5" y="5" width="8" height="14" rx="1.2" fill="none" stroke="currentColor" stroke-width="1.7" />
        </svg>
      </button>
    </div>
    <label class="doc-nav-btn upload" :class="{ busy: uploading }" :title="uploading ? t('doc.uploading') : t('doc.upload')">
      <svg class="doc-nav-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 16V6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        <path d="M8 9.5 12 5.5 16 9.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M5 19h14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
      </svg>
      <span class="sr">{{ uploading ? t('doc.uploading') : t('doc.upload') }}</span>
      <input ref="input" type="file" hidden multiple :disabled="uploading" @change="onPick" />
    </label>
    <label class="doc-search">
      <svg class="doc-search-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" stroke-width="1.7" />
        <path d="M15.5 15.5 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
      </svg>
      <input
        v-model="draft"
        type="search"
        class="doc-search-input"
        :placeholder="t('doc.search')"
        :aria-label="t('doc.search')"
        @keydown.escape.prevent="draft = ''"
      />
    </label>
  </div>
</template>

<style scoped>
.doc-nav {
  display: flex;
  align-items: center;
  align-self: center;
  gap: 8px;
  height: 30px;
}
.doc-modes {
  display: flex;
  align-items: stretch;
  height: 30px;
  padding: 2px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
}
.doc-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 100%;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--muted, #6b6458);
  cursor: pointer;
}
.doc-nav-btn:hover {
  color: var(--ink, #1c1914);
}
.doc-nav-btn.active {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 14%, #fff);
  color: var(--accent, #0f6a5a);
}
.doc-nav-btn.upload {
  width: 30px;
  height: 30px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
}
.doc-nav-btn.busy {
  opacity: 0.6;
  cursor: wait;
}
.doc-nav-icon {
  width: 16px;
  height: 16px;
  display: block;
}
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.doc-search {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  width: 180px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
  color: var(--muted, #6b6458);
}
.doc-search-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}
.doc-search-input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: 0.85rem;
  color: var(--ink, #1c1914);
}
.doc-search-input::-webkit-search-decoration,
.doc-search-input::-webkit-search-cancel-button {
  appearance: none;
}
</style>
