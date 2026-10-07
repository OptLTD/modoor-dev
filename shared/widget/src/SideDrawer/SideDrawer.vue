<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useI18n } from '@modoor/hooks'

const props = withDefaults(
  defineProps<{
    open: boolean
    title?: string
    width?: string
  }>(),
  {
    title: '',
    width: '360px',
  },
)

const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open) window.addEventListener('keydown', onKey)
    else window.removeEventListener('keydown', onKey)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="sd-mask" @click.self="emit('close')">
      <aside class="sd-panel" role="dialog" aria-modal="true" :aria-label="title" :style="{ width }">
        <header class="sd-head">
          <strong class="sd-title truncate">{{ title }}</strong>
          <div v-if="$slots.extra" class="sd-extra">
            <slot name="extra" />
          </div>
          <button type="button" class="sd-close" @click="emit('close')">
            {{ t('widget.close') }}
          </button>
        </header>
        <div class="sd-body">
          <slot />
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.sd-mask {
  position: fixed;
  inset: 0;
  z-index: 10080;
  background: color-mix(in srgb, var(--ink, #1c1914) 28%, transparent);
  display: flex;
  justify-content: flex-end;
}
.sd-panel {
  max-width: 100vw;
  height: 100%;
  background: var(--panel, #fff);
  border-left: 1px solid var(--line, #e2e6eb);
  box-shadow: -8px 0 24px rgba(28, 25, 23, 0.12);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sd-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
  min-height: 48px;
}
.sd-title {
  font-size: 0.95rem;
  min-width: 0;
}
.sd-extra {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sd-close {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--ink, #1c1914);
  text-decoration: underline;
  cursor: pointer;
  font-size: 13px;
  flex-shrink: 0;
  margin-left: auto;
}
.sd-extra + .sd-close {
  margin-left: 0;
}
.sd-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
