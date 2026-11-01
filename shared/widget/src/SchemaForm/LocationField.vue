<script setup lang="ts">
/**
 * LOCATION field — address autocomplete backed by the server map proxy.
 *
 * The typed text is still the stored value, so manual entry keeps working when
 * no provider is configured. Picking a suggestion also emits the coordinates so
 * SchemaForm can fill optional sibling lat/lng fields.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  formatLocationValue,
  loadMapConfig,
  locationDisplayText,
  searchPlaces,
  t,
  type MapConfig,
  type PlaceResult,
} from '@modoor/hooks'
import SvgIcon from '../SvgIcon/SvgIcon.vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    disabled?: boolean
    placeholder?: string
    /** Optional region bias, e.g. extra.mapRegion = "连云港". */
    region?: string
  }>(),
  { modelValue: '', disabled: false, placeholder: '', region: '' },
)

const emit = defineEmits<{
  'update:modelValue': [string]
  select: [PlaceResult]
}>()

const rootEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const panelStyle = ref<Record<string, string>>({})
const query = ref(locationDisplayText(props.modelValue))
const open = ref(false)
const loading = ref(false)
const error = ref('')
const searched = ref(false)
const active = ref(-1)
const results = ref<PlaceResult[]>([])
const config = ref<MapConfig | null>(null)

let debounce: ReturnType<typeof setTimeout> | null = null
let requestSeq = 0

watch(
  () => props.modelValue,
  (value) => {
    const text = locationDisplayText(value)
    if (text !== query.value) query.value = text
  },
)

const providerLabel = computed(() => {
  const id = results.value[0]?.provider || config.value?.provider || ''
  return config.value?.providers.find((p) => p.id === id)?.label || id
})

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

async function ensureConfig() {
  if (config.value) return
  try {
    config.value = await loadMapConfig()
  } catch (err) {
    error.value = errorText(err)
  }
}

function updatePanelPos() {
  const el = inputEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const maxH = 320
  const spaceBelow = window.innerHeight - r.bottom - 8
  const placeUp = spaceBelow < 180 && r.top > spaceBelow
  panelStyle.value = {
    position: 'fixed',
    left: `${Math.max(8, r.left)}px`,
    width: `${Math.max(r.width, 240)}px`,
    zIndex: 'var(--z-pop, 10120)',
    ...(placeUp
      ? {
          bottom: `${window.innerHeight - r.top + 4}px`,
          top: 'auto',
          maxHeight: `${Math.min(maxH, r.top - 8)}px`,
        }
      : {
          top: `${r.bottom + 4}px`,
          bottom: 'auto',
          maxHeight: `${Math.min(maxH, spaceBelow)}px`,
        }),
  }
}

async function openPanel() {
  if (props.disabled) return
  open.value = true
  await nextTick()
  updatePanelPos()
}

function clearDebounce() {
  if (debounce) {
    clearTimeout(debounce)
    debounce = null
  }
}

function scheduleSearch(delay = 320) {
  clearDebounce()
  const text = query.value.trim()
  if (!text) return
  debounce = setTimeout(() => {
    debounce = null
    void runSearch(text)
  }, delay)
}

async function runSearch(text: string) {
  if (props.disabled) return
  await ensureConfig()
  if (text !== query.value.trim()) return
  if (config.value && !config.value.configured) {
    await openPanel()
    return
  }
  const seq = ++requestSeq
  loading.value = true
  error.value = ''
  searched.value = false
  active.value = -1
  await openPanel()
  try {
    const payload = await searchPlaces(text, {
      region: props.region,
      limit: 8,
    })
    if (seq !== requestSeq) return
    results.value = payload.results || []
    searched.value = true
  } catch (err) {
    if (seq !== requestSeq) return
    results.value = []
    searched.value = true
    error.value = errorText(err)
  } finally {
    if (seq === requestSeq) {
      loading.value = false
      await nextTick()
      updatePanelPos()
    }
  }
}

function onInput() {
  emit('update:modelValue', query.value)
  error.value = ''
  active.value = -1
  const text = query.value.trim()
  if (!text) {
    clearDebounce()
    requestSeq += 1
    results.value = []
    searched.value = false
    open.value = false
    return
  }
  void openPanel()
  scheduleSearch()
}

async function onFocus() {
  if (props.disabled) return
  await ensureConfig()
  await openPanel()
  if (query.value.trim() && !results.value.length && !loading.value) scheduleSearch(0)
}

function pick(item: PlaceResult) {
  const display = item.name || item.address || item.label
  const address = item.address || item.name || item.label
  query.value = display
  emit(
    'update:modelValue',
    formatLocationValue({
      display,
      address,
      lat: item.lat,
      lng: item.lng,
    }),
  )
  emit('select', item)
  clearDebounce()
  requestSeq += 1
  open.value = false
  loading.value = false
  results.value = []
  searched.value = false
  active.value = -1
}

async function scrollActiveIntoView() {
  await nextTick()
  panelEl.value
    ?.querySelector<HTMLElement>('.location-option.active')
    ?.scrollIntoView({ block: 'nearest' })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    open.value = false
    return
  }
  if (e.key === 'Enter') {
    const item = results.value[active.value >= 0 ? active.value : 0]
    if (open.value && item) {
      e.preventDefault()
      pick(item)
    }
    return
  }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  if (props.disabled) return
  if (!open.value) {
    void openPanel()
    return
  }
  const count = results.value.length
  if (!count) return
  if (e.key === 'ArrowDown') {
    active.value = active.value + 1 >= count ? 0 : active.value + 1
  } else {
    active.value = active.value - 1 < 0 ? count - 1 : active.value - 1
  }
  void scrollActiveIntoView()
}

function onDocPointer(e: Event) {
  const target = e.target as Node
  if (rootEl.value?.contains(target)) return
  if (panelEl.value?.contains(target)) return
  open.value = false
}

function onScrollOrResize() {
  if (open.value) updatePanelPos()
}

watch(open, (value) => {
  if (value) {
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
  } else {
    window.removeEventListener('scroll', onScrollOrResize, true)
    window.removeEventListener('resize', onScrollOrResize)
  }
})

onMounted(() => {
  document.addEventListener('mousedown', onDocPointer)
})

onBeforeUnmount(() => {
  clearDebounce()
  document.removeEventListener('mousedown', onDocPointer)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<template>
  <div ref="rootEl" class="location-field" :class="{ disabled }">
    <div class="location-input-wrap">
      <input
        ref="inputEl"
        v-model="query"
        type="search"
        class="location-input"
        :placeholder="placeholder || t('widget.mapSearchPlaceholder')"
        :disabled="disabled"
        autocomplete="off"
        role="combobox"
        :aria-expanded="open"
        aria-autocomplete="list"
        @input="onInput"
        @focus="onFocus"
        @click="onFocus"
        @keydown="onKeydown"
      />
      <span v-if="loading" class="location-spinner" aria-hidden="true" />
      <SvgIcon
        v-else-if="config?.configured"
        class="location-icon"
        name="search"
        :size="13"
      />
    </div>

    <Teleport to="body">
      <div v-if="open" ref="panelEl" class="location-panel" :style="panelStyle">
        <div v-if="loading" class="location-state">{{ t('widget.mapSearching') }}</div>
        <div v-else-if="error" class="location-state error">{{ error }}</div>
        <template v-else-if="results.length">
          <button
            v-for="(item, i) in results"
            :key="`${item.provider}:${item.id || i}`"
            type="button"
            class="location-option"
            :class="{ active: i === active }"
            @mouseenter="active = i"
            @mousedown.prevent="pick(item)"
          >
            <span class="location-option-name">{{ item.name || item.address }}</span>
            <span
              v-if="item.address && item.address !== item.name"
              class="location-option-address"
            >{{ item.address }}</span>
          </button>
          <div class="location-attribution">
            {{ t('widget.mapPoweredBy', { provider: providerLabel }) }}
          </div>
        </template>
        <div v-else-if="config && !config.configured" class="location-state hint">
          {{ t('widget.mapNotConfigured') }}
        </div>
        <div v-else-if="searched" class="location-state">{{ t('widget.mapNoResults') }}</div>
        <div v-else class="location-state hint">{{ t('widget.mapPickHint') }}</div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.location-field {
  flex: 1;
  width: 100%;
  min-width: 0;
}
.location-input-wrap {
  position: relative;
  display: flex;
  width: 100%;
}
.location-input {
  width: 100%;
  min-height: 32px;
  border: 0;
  border-bottom: 1px solid #c5cad3;
  border-radius: 0;
  padding: 5px 28px 5px 8px;
  font: inherit;
  font-size: 0.88rem;
  color: var(--ink, #1c1914);
  background: #fff;
  outline: none;
  transition:
    border-color 0.12s ease,
    background 0.12s ease;
}
.location-input:focus {
  border-bottom-color: var(--accent, #0f6a5a);
}
.location-input:disabled {
  color: var(--muted, #6b6458);
  background: #eef1f4;
  border-bottom-color: #d5dae2;
  cursor: not-allowed;
}
.location-icon {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted, #6b6458);
  pointer-events: none;
}
.location-spinner {
  position: absolute;
  right: 9px;
  top: 50%;
  width: 12px;
  height: 12px;
  margin-top: -6px;
  border: 2px solid #d5dae2;
  border-top-color: var(--accent, #0f6a5a);
  border-radius: 50%;
  animation: location-spin 0.7s linear infinite;
}
@keyframes location-spin {
  to {
    transform: rotate(360deg);
  }
}
.location-panel {
  overflow: auto;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-lg, 8px);
  background: #fff;
  box-shadow: var(--shadow, 0 12px 40px rgba(40, 30, 10, 0.08));
  padding: 4px;
  box-sizing: border-box;
}
.location-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  border: 0;
  border-radius: var(--radius-sm, 4px);
  background: transparent;
  padding: 6px 8px;
  text-align: left;
  font: inherit;
  color: var(--ink, #1c1914);
  cursor: pointer;
}
.location-option.active,
.location-option:hover {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 10%, #fff);
}
.location-option-name {
  font-size: 0.86rem;
  font-weight: 500;
  line-height: 1.35;
  word-break: break-word;
}
.location-option-address {
  font-size: 0.76rem;
  line-height: 1.35;
  color: var(--muted, #6b6458);
  word-break: break-word;
}
.location-state {
  padding: 10px 8px;
  font-size: 0.82rem;
  line-height: 1.4;
  color: var(--muted, #6b6458);
}
.location-state.hint {
  color: var(--muted, #6b6458);
}
.location-state.error {
  color: var(--danger, #a33b2b);
}
.location-attribution {
  margin-top: 2px;
  padding: 4px 8px 2px;
  border-top: 1px solid var(--line, #e2e6eb);
  font-size: 0.72rem;
  color: var(--muted, #6b6458);
  text-align: right;
}
</style>
