<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from '@modoor/hooks'
import {
  chooseAll,
  chooseModel,
  chooseModelEmpty,
  chooseTag,
  chooseTagEmpty,
  docFilter,
  modelEmpty,
  models,
  navError,
  tagEmpty,
  tags,
} from './library'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const canBack = ref(false)
const canForward = ref(false)
const modelsOpen = ref(true)
const tagsOpen = ref(true)
const navQuery = ref('')
const needle = computed(() => navQuery.value.trim().toLowerCase())

function matches(text: string) {
  if (!needle.value) return true
  return text.toLowerCase().includes(needle.value)
}

const shownModels = computed(() =>
  models.value.filter((item) => matches(item.title || item.model) || matches(item.model)),
)
const shownTags = computed(() => tags.value.filter((item) => matches(item.tag)))
const showModelEmpty = computed(() => matches(t('doc.navModelEmpty')))
const showTagEmpty = computed(() => matches(t('doc.navTagEmpty')))
const showModels = computed(() => !needle.value || showModelEmpty.value || shownModels.value.length > 0)
const showTags = computed(() => !needle.value || showTagEmpty.value || shownTags.value.length > 0)

watch(needle, (value) => {
  if (!value) return
  modelsOpen.value = true
  tagsOpen.value = true
})

function syncHistory() {
  const state = window.history.state as { back?: string | null; forward?: string | null } | null
  canBack.value = Boolean(state?.back)
  canForward.value = Boolean(state?.forward)
}

function goHome() {
  chooseAll()
  if (route.name !== 'doc.folder') void router.push({ name: 'doc.folder' })
}

onMounted(syncHistory)
watch(() => route.fullPath, syncHistory)

function backToFolder() {
  if (route.name === 'doc.preview') void router.push({ name: 'doc.folder' })
}

function pickModel(model: string) {
  chooseModel(model)
  backToFolder()
}

function pickModelEmpty() {
  chooseModelEmpty()
  backToFolder()
}

function pickTag(tag: string) {
  chooseTag(tag)
  backToFolder()
}

function pickTagEmpty() {
  chooseTagEmpty()
  backToFolder()
}

function modelActive(model: string) {
  const current = docFilter.value
  return current.kind === 'model' && current.model === model
}

function tagActive(tag: string) {
  const current = docFilter.value
  return current.kind === 'tag' && current.tag === tag
}
</script>

<template>
  <aside class="sidebar">
    <header class="side-head">
      <button type="button" class="side-home" :title="t('doc.library')" @click="goHome">
        <svg class="side-home-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 11.5 12 4l8 7.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
          <path d="M7 10.5V19h10v-8.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" />
        </svg>
        <span>{{ t('doc.library') }}</span>
      </button>
      <div class="side-history">
        <button
          type="button"
          class="side-step"
          :disabled="!canBack"
          :title="t('doc.navBack')"
          :aria-label="t('doc.navBack')"
          @click="router.back()"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M14 6 8 12l6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button
          type="button"
          class="side-step"
          :disabled="!canForward"
          :title="t('doc.navForward')"
          :aria-label="t('doc.navForward')"
          @click="router.forward()"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M10 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </header>
    <nav class="doc-side" :aria-label="t('doc.library')">
      <div class="side-split" role="separator" />
      <label class="side-filter">
        <input
          v-model="navQuery"
          type="search"
          :placeholder="t('doc.navFilter')"
          :aria-label="t('doc.navFilter')"
        />
      </label>
      <button
        v-if="showModels"
        type="button"
        class="side-label"
        :aria-expanded="modelsOpen"
        @click="modelsOpen = !modelsOpen"
      >
        <svg class="side-caret" :class="{ closed: !modelsOpen }" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 10l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span>{{ t('doc.navModels') }}</span>
      </button>
      <template v-if="modelsOpen">
        <button
          v-if="showModelEmpty"
          type="button"
          class="side-item"
          :class="{ active: docFilter.kind === 'model-empty' }"
          :aria-pressed="docFilter.kind === 'model-empty'"
          @click="pickModelEmpty"
        >
          <span class="side-name">{{ t('doc.navModelEmpty') }}</span>
          <span class="muted">{{ modelEmpty }}</span>
        </button>
        <button
          v-for="item in shownModels"
          :key="item.model"
          type="button"
          class="side-item"
          :class="{ active: modelActive(item.model) }"
          :aria-pressed="modelActive(item.model)"
          :title="item.title || item.model"
          @click="pickModel(item.model)"
        >
          <span class="side-name">{{ item.title || item.model }}</span>
          <span class="muted">{{ item.count }}</span>
        </button>
      </template>

      <button
        v-if="showTags"
        type="button"
        class="side-label"
        :aria-expanded="tagsOpen"
        @click="tagsOpen = !tagsOpen"
      >
        <svg class="side-caret" :class="{ closed: !tagsOpen }" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 10l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span>{{ t('doc.navTags') }}</span>
      </button>
      <template v-if="tagsOpen">
        <button
          v-if="showTagEmpty"
          type="button"
          class="side-item"
          :class="{ active: docFilter.kind === 'tag-empty' }"
          :aria-pressed="docFilter.kind === 'tag-empty'"
          @click="pickTagEmpty"
        >
          <span class="side-name">{{ t('doc.navTagEmpty') }}</span>
          <span class="muted">{{ tagEmpty }}</span>
        </button>
        <button
          v-for="item in shownTags"
          :key="item.tag"
          type="button"
          class="side-item"
          :class="{ active: tagActive(item.tag) }"
          :aria-pressed="tagActive(item.tag)"
          :title="item.tag"
          @click="pickTag(item.tag)"
        >
          <span class="side-name">{{ item.tag }}</span>
          <span class="muted">{{ item.count }}</span>
        </button>
      </template>
    </nav>
    <p v-if="navError" class="error side-error">{{ navError }}</p>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #fff;
  box-sizing: border-box;
  border-right: 1px solid var(--line, #e2e6eb);
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  height: 44px;
  margin: 0;
  padding: 0 6px 0 8px;
  box-sizing: border-box;
  margin-right: -1px;
  border-right: 1px solid var(--line, #e2e6eb);
}
.side-home {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin: 0;
  padding: 4px 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--ink, #1c1914);
  font: inherit;
  font-size: 0.92rem;
  font-weight: 600;
  cursor: pointer;
}
.side-home:hover {
  background: color-mix(in srgb, var(--ink, #1c1914) 6%, transparent);
}
.side-home span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.side-home-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
.side-history {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.side-step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--ink, #1c1914);
  cursor: pointer;
}
.side-step svg {
  width: 16px;
  height: 16px;
  display: block;
}
.side-step:hover:not(:disabled) {
  background: color-mix(in srgb, var(--ink, #1c1914) 6%, transparent);
}
.side-step:disabled {
  color: var(--muted, #6b6458);
  opacity: 0.35;
  cursor: default;
}
.doc-side {
  flex: 1 1 auto;
  align-self: stretch;
  width: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0 6px 12px;
  border: 0;
  background: transparent;
  overflow: auto;
  box-sizing: border-box;
}
.side-split {
  margin: 2px 6px;
  border-bottom: 1px solid var(--line, #e2e6eb);
}
.side-filter {
  display: block;
  flex-shrink: 0;
  margin: 0 6px;
  padding: 8px 0 4px;
}
.side-filter input {
  width: 100%;
  box-sizing: border-box;
  height: 30px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  padding: 0 10px;
  background: #fff;
  color: var(--ink, #1c1914);
  font: inherit;
  font-size: 0.85rem;
}
.side-filter input:focus {
  outline: none;
  border-color: var(--accent, #0f6a5a);
}
.side-filter input::-webkit-search-decoration,
.side-filter input::-webkit-search-cancel-button {
  appearance: none;
}
.side-label {
  display: flex;
  align-items: center;
  gap: 2px;
  width: 100%;
  margin: 10px 0 2px;
  padding: 4px 6px;
  border: 0;
  background: transparent;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--muted, #6b6458);
  cursor: pointer;
  text-align: left;
}
.side-label:hover {
  color: var(--ink, #1c1914);
}
.side-caret {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.side-caret.closed {
  transform: rotate(-90deg);
}
.side-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 7px 8px;
  border-radius: var(--radius-md, 6px);
  font: inherit;
  font-size: 0.88rem;
  cursor: pointer;
  color: var(--ink, #1c1914);
}
.side-item:hover {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 8%, transparent);
}
.side-item.active {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 14%, transparent);
  color: var(--accent, #0f6a5a);
  font-weight: 600;
}
.side-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.muted {
  color: var(--muted, #6b6458);
  font-size: 0.78rem;
  font-weight: 500;
  flex-shrink: 0;
}
.side-item.active .muted {
  color: var(--accent, #0f6a5a);
}
.side-error {
  margin: 0;
  font-size: 0.82rem;
}
</style>
