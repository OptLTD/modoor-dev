<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '@modoor/hooks'

export type ViewerItem = {
  src: string
  name: string
  kind: 'image' | 'pdf' | 'file'
}

const props = defineProps<{
  items: ViewerItem[]
  index: number
  removable?: boolean
}>()

const emit = defineEmits<{
  close: []
  remove: [number]
  'update:index': [number]
}>()

const root = ref<HTMLElement | null>(null)
const current = computed(() => props.items[props.index] || null)
const total = computed(() => props.items.length)

function prev() {
  if (props.index <= 0) return
  emit('update:index', props.index - 1)
}

function next() {
  if (props.index >= total.value - 1) return
  emit('update:index', props.index + 1)
}

function onKey(event: KeyboardEvent) {
  if (event.key !== 'Escape' && event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  event.stopPropagation()
  if (event.key === 'Escape') emit('close')
  else if (event.key === 'ArrowLeft') prev()
  else next()
}

watch(
  () => props.items.length,
  (count) => {
    if (!count) emit('close')
    else if (props.index > count - 1) emit('update:index', count - 1)
  },
)

onMounted(() => {
  root.value?.focus()
})
window.addEventListener('keydown', onKey, true)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey, true))
</script>

<template>
  <Teleport to="body">
    <div
      ref="root"
      class="viewer"
      role="dialog"
      tabindex="-1"
      aria-modal="true"
      @keydown="onKey"
      @click.self="emit('close')"
    >
      <header class="viewer-bar">
        <strong class="viewer-name">{{ current?.name }}</strong>
        <span class="viewer-count">{{ index + 1 }} / {{ total }}</span>
        <button type="button" class="viewer-close" @click="emit('close')">{{ t('widget.close') }}</button>
      </header>
      <div class="viewer-stage">
        <img
          v-if="current && current.kind === 'image'"
          class="viewer-image"
          :src="current.src"
          :alt="current.name"
        />
        <iframe
          v-else-if="current && current.kind === 'pdf'"
          class="viewer-frame"
          :src="current.src"
          :title="current.name"
        />
        <a v-else-if="current" class="viewer-file" :href="current.src" target="_blank" rel="noopener">
          {{ current.name }}
        </a>
      </div>
      <footer class="viewer-bar">
        <button type="button" class="viewer-nav" :disabled="index <= 0" @click="prev">
          {{ t('widget.prevFile') }}
        </button>
        <button
          v-if="removable"
          type="button"
          class="viewer-remove"
          @click="emit('remove', index)"
        >
          {{ t('widget.removeFile') }}
        </button>
        <button type="button" class="viewer-nav" :disabled="index >= total - 1" @click="next">
          {{ t('widget.nextFile') }}
        </button>
      </footer>
    </div>
  </Teleport>
</template>

<style scoped>
.viewer {
  position: fixed;
  inset: 0;
  z-index: 10100;
  display: flex;
  flex-direction: column;
  background: rgba(20, 18, 14, 0.86);
  color: #fff;
}
.viewer-bar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}
.viewer-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.viewer-count {
  flex: 0 0 auto;
  color: rgba(255, 255, 255, 0.72);
  font-variant-numeric: tabular-nums;
}
.viewer-close,
.viewer-nav,
.viewer-remove {
  flex: 0 0 auto;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: transparent;
  color: #fff;
  border-radius: 4px;
  padding: 4px 10px;
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
}
.viewer-close:hover,
.viewer-nav:hover:not(:disabled),
.viewer-remove:hover {
  background: rgba(255, 255, 255, 0.12);
}
.viewer-nav:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.viewer-stage {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 24px 8px;
}
.viewer-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  background: #111;
}
.viewer-frame {
  width: min(960px, 100%);
  height: 100%;
  border: 0;
  background: #fff;
}
.viewer-file {
  color: #fff;
  font-size: 1rem;
}
.viewer-bar:last-child {
  justify-content: center;
}
</style>
