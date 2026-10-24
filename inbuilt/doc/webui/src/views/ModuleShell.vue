<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from '@modoor/hooks'
import DocSidebar from './DocSidebar.vue'
import { refreshNav, uploadDocFiles } from './library'

const { t } = useI18n()
const router = useRouter()
const dragOver = ref(false)
let dragDepth = 0

onMounted(() => {
  void refreshNav()
})

function onDragEnter(ev: DragEvent) {
  if (!ev.dataTransfer?.types.includes('Files')) return
  dragDepth += 1
  dragOver.value = true
}

function onDragOver(ev: DragEvent) {
  if (!ev.dataTransfer?.types.includes('Files')) return
  ev.dataTransfer.dropEffect = 'copy'
  dragOver.value = true
}

function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragOver.value = false
}

async function onDrop(ev: DragEvent) {
  dragDepth = 0
  dragOver.value = false
  const files = Array.from(ev.dataTransfer?.files || [])
  const lastId = await uploadDocFiles(files)
  if (lastId) void router.push(`/mod/doc/${encodeURIComponent(lastId)}`)
}
</script>

<template>
  <section
    class="doc-frame"
    :class="{ 'drag-over': dragOver }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent="onDragOver"
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div v-if="dragOver" class="drop-overlay" aria-hidden="true">
      <p>{{ t('doc.dropToUpload') }}</p>
    </div>
    <DocSidebar />
    <div class="doc-main">
      <RouterView />
    </div>
  </section>
</template>

<style scoped>
.doc-frame {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(200px, 240px) minmax(0, 1fr);
  position: relative;
  overflow: hidden;
  margin: -16px;
}
.doc-frame.drag-over {
  outline: 2px dashed var(--accent, #2563eb);
  outline-offset: -6px;
}
.doc-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel, #fff);
}
.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--accent, #2563eb) 12%, transparent);
  pointer-events: none;
}
.drop-overlay p {
  margin: 0;
  padding: 0.75rem 1.25rem;
  border-radius: var(--radius-lg, 8px);
  background: var(--panel, #fff);
  border: 1px solid var(--line, #ddd);
  font-weight: 600;
}
</style>
