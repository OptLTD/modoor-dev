<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 有文案时用默认按钮；日期区间等自定义触发器走 trigger 插槽 */
    label?: string
    buttonClass?: string
    align?: 'start' | 'end'
    minWidth?: number
    maxWidth?: number
    /** 面板里继续操作时不关闭，日期区间用 */
    keepOpen?: boolean
    /** 触发按钮拉满父级宽度，纵向按钮组用 */
    wide?: boolean
  }>(),
  {
    label: '',
    buttonClass: '',
    align: 'start',
    minWidth: 152,
    maxWidth: 320,
    keepOpen: false,
    wide: false,
  },
)

const open = ref(false)
const triggerEl = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const panelStyle = ref<Record<string, string>>({})
const mine = Symbol('dropdown')

function close() {
  open.value = false
}

function announce() {
  window.dispatchEvent(new CustomEvent('widget-dropdown', { detail: mine }))
}

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  announce()
  await nextTick()
  place()
}

function place() {
  const el = triggerEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const maxH = 360
  const spaceBelow = window.innerHeight - rect.bottom - 8
  const placeUp = spaceBelow < 300 && rect.top > spaceBelow
  const minWidth = Math.max(rect.width, props.minWidth)
  const maxWidth = Math.max(props.maxWidth, rect.width)
  panelStyle.value = {
    position: 'fixed',
    zIndex: 'var(--z-pop, 10120)',
    minWidth: `${minWidth}px`,
    maxWidth: `${maxWidth}px`,
    ...(props.align === 'end'
      ? { right: `${Math.max(8, window.innerWidth - rect.right)}px`, left: 'auto' }
      : { left: `${Math.max(8, rect.left)}px`, right: 'auto' }),
    ...(placeUp
      ? {
          bottom: `${window.innerHeight - rect.top + 4}px`,
          top: 'auto',
          maxHeight: `${Math.min(maxH, rect.top - 8)}px`,
        }
      : {
          top: `${rect.bottom + 4}px`,
          bottom: 'auto',
          maxHeight: `${Math.min(maxH, spaceBelow)}px`,
        }),
  }
}

function onPanelClick(event: MouseEvent) {
  if (props.keepOpen) return
  const el = event.target as HTMLElement | null
  if (el?.closest('button, [role="menuitem"]')) close()
}

function onDocPointer(event: Event) {
  const node = event.target as Node | null
  if (!node) return
  if (triggerEl.value?.contains(node) || panelEl.value?.contains(node)) return
  close()
}

function onOther(event: Event) {
  if ((event as CustomEvent).detail !== mine) close()
}

function onScrollOrResize() {
  if (open.value) place()
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
  document.addEventListener('pointerdown', onDocPointer)
  window.addEventListener('widget-dropdown', onOther)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  window.removeEventListener('widget-dropdown', onOther)
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})
</script>

<template>
  <div class="dropdown" :class="{ open, wide }">
    <div ref="triggerEl" class="dropdown-trigger" @click="toggle">
      <slot name="trigger" :open="open" :toggle="toggle">
        <button
          type="button"
          class="btn"
          :class="buttonClass"
          :aria-expanded="open"
          :aria-haspopup="true"
        >
          {{ label }}
          <span class="dropdown-caret" aria-hidden="true">▾</span>
        </button>
      </slot>
    </div>
    <Teleport to="body">
      <div
        v-if="open"
        ref="panelEl"
        class="dropdown-panel"
        :class="{ 'dropdown-panel--loose': keepOpen }"
        :role="keepOpen ? undefined : 'menu'"
        :style="panelStyle"
        @click="onPanelClick"
      >
        <slot :close="close" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.dropdown {
  position: relative;
}
.dropdown-trigger {
  display: inline-flex;
  max-width: 100%;
}
.dropdown-trigger > :deep(.btn) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.dropdown.open > .dropdown-trigger > :deep(.btn) {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
  background: #eef6f3;
}
.dropdown-caret {
  font-size: 0.7rem;
  opacity: 0.7;
}
.dropdown.wide,
.dropdown.wide > .dropdown-trigger {
  width: 100%;
}
.dropdown.wide > .dropdown-trigger {
  display: flex;
}
.dropdown.wide > .dropdown-trigger > :deep(.btn) {
  width: 100%;
  justify-content: center;
}
</style>

<style>
.dropdown-panel {
  overflow: auto;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-lg, 8px);
  background: var(--panel, #fff);
  box-shadow: var(--shadow, 0 8px 24px rgba(28, 25, 23, 0.12));
  padding: 4px;
}
.dropdown-panel--loose {
  padding: 0.5rem;
}
.dropdown-panel .dropdown-item {
  display: block;
  width: 100%;
  white-space: nowrap;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 7px 10px;
  border-radius: var(--radius-md, 6px);
  font: inherit;
  font-size: 0.88rem;
  cursor: pointer;
  color: inherit;
}
.dropdown-panel .dropdown-item:hover:not(:disabled) {
  background: #eef6f3;
  color: var(--accent, #0f6a5a);
}
.dropdown-panel .dropdown-item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.dropdown-panel .dropdown-item.danger {
  color: var(--danger, #a33b2b);
}
</style>
