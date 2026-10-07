<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { assetContentUrl, t, useRecordGateway, type UploadedFile } from '@modoor/hooks'
import ImageViewer, { type ViewerItem } from '../ImageViewer/ImageViewer.vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string | string[]
    multiple?: boolean
    accept?: string
    disabled?: boolean
    tags?: string[]
  }>(),
  { modelValue: '', multiple: false, accept: '', disabled: false, tags: () => [] },
)

const emit = defineEmits<{
  'update:modelValue': [string | string[]]
}>()

const gateway = useRecordGateway()
const input = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const error = ref('')
const known = reactive<Record<string, UploadedFile>>({})
const viewerOpen = ref(false)
const viewerIndex = ref(0)

const ids = computed(() => {
  const value = props.modelValue
  if (Array.isArray(value)) return value.map((item) => String(item || '').trim()).filter(Boolean)
  const text = String(value || '').trim()
  return text ? [text] : []
})

function write(next: string[]) {
  if (props.multiple) emit('update:modelValue', next)
  else emit('update:modelValue', next[0] || '')
}

function openPicker() {
  if (props.disabled || busy.value) return
  input.value?.click()
}

function kindOf(id: string): ViewerItem['kind'] {
  const mime = known[id]?.mime_type || ''
  const name = (known[id]?.filename || '').toLowerCase()
  if (mime.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp)$/.test(name)) return 'image'
  if (mime === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  return 'file'
}

const viewerItems = computed<ViewerItem[]>(() =>
  ids.value.map((id) => ({
    src: assetContentUrl(id),
    name: labelOf(id),
    kind: kindOf(id),
  })),
)

function openViewer() {
  if (!ids.value.length) return
  viewerIndex.value = 0
  viewerOpen.value = true
}

function onViewerRemove(index: number) {
  const id = ids.value[index]
  if (!id) return
  remove(id)
}

function labelOf(id: string) {
  return known[id]?.filename || known[id]?.title || id
}

async function remember(id: string) {
  if (!id || known[id]) return
  try {
    known[id] = await gateway.fetchAsset(id)
  } catch {
    known[id] = { id, filename: id, title: id, mime_type: '' }
  }
}

watch(
  ids,
  (list) => {
    for (const id of list) void remember(id)
  },
  { immediate: true },
)

async function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  const files = [...(target.files || [])]
  target.value = ''
  if (!files.length || props.disabled) return
  busy.value = true
  error.value = ''
  try {
    const picked = props.multiple ? files : files.slice(0, 1)
    const uploaded: string[] = []
    for (const file of picked) {
      const asset = await gateway.uploadAsset(file, { tags: props.tags })
      known[asset.id] = asset
      uploaded.push(asset.id)
    }
    write(props.multiple ? [...ids.value, ...uploaded] : uploaded)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

function remove(id: string) {
  write(ids.value.filter((item) => item !== id))
}
</script>

<template>
  <div class="file-field">
    <div class="file-actions">
      <button
        type="button"
        class="file-act"
        :disabled="disabled || busy"
        @click="openPicker"
      >
        {{ busy ? t('widget.uploading') : t('widget.upload') }}
      </button>
      <span class="file-split" aria-hidden="true">|</span>
      <button
        type="button"
        class="file-act"
        :disabled="!ids.length"
        @click="openViewer"
      >
        {{ t('widget.viewFiles', { n: ids.length }) }}
      </button>
    </div>
    <input
      ref="input"
      class="file-input"
      type="file"
      :accept="accept || undefined"
      :multiple="multiple"
      :disabled="disabled"
      @change="onPick"
    />
    <p v-if="error" class="file-error">{{ error }}</p>
    <ImageViewer
      v-if="viewerOpen"
      :items="viewerItems"
      :index="viewerIndex"
      :removable="!disabled"
      @close="viewerOpen = false"
      @update:index="viewerIndex = $event"
      @remove="onViewerRemove"
    />
  </div>
</template>

<style scoped>
.file-field {
  flex: 1 1 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  min-height: 32px;
}
.file-actions {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 4px;
  background: #fff;
  overflow: hidden;
}
.file-act {
  border: 0;
  background: transparent;
  color: var(--accent, #0f6a5a);
  padding: 3px 8px;
  font: inherit;
  font-size: 0.82rem;
  line-height: 1.3;
  cursor: pointer;
  white-space: nowrap;
}
.file-act:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 8%, #fff);
}
.file-act:disabled {
  color: #b0b6bf;
  cursor: not-allowed;
  background: transparent;
}
.file-split {
  color: #c5cad3;
  line-height: 1;
  user-select: none;
}
.file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.file-error {
  flex: 1 0 100%;
  margin: 0;
  color: var(--danger, #a33b2b);
  font-size: 0.78rem;
  line-height: 1.3;
}
</style>
