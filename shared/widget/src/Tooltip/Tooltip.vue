<script setup lang="ts">
/**
 * Small hover/focus help marker with an immediate tooltip.
 *
 * Native `title` waits before showing; this renders a fixed-position tooltip
 * through Teleport so it is visible immediately and never clipped by cards.
 */
import { reactive } from 'vue'

const props = withDefaults(
  defineProps<{
    text?: string
    label?: string
    maxWidth?: number
  }>(),
  {
    text: '',
    label: '?',
    maxWidth: 360,
  },
)

const state = reactive({
  open: false,
  text: '',
  top: 0,
  left: 0,
  above: true,
})

function show(event: MouseEvent | FocusEvent) {
  if (!props.text) return
  const target = event.currentTarget as HTMLElement | null
  if (!target) return
  const rect = target.getBoundingClientRect()
  const above = rect.top > 96
  const half = Math.min(props.maxWidth / 2, window.innerWidth / 2 - 8)
  state.text = props.text
  state.above = above
  state.top = above ? rect.top - 8 : rect.bottom + 8
  state.left = Math.min(
    Math.max(rect.left + rect.width / 2, half + 8),
    window.innerWidth - half - 8,
  )
  state.open = true
}

function hide() {
  state.open = false
}
</script>

<template>
  <span
    class="tooltip-trigger"
    tabindex="0"
    @mouseenter="show"
    @mouseleave="hide"
    @focus="show"
    @blur="hide"
  >
    <slot>{{ label }}</slot>
  </span>
  <Teleport to="body">
    <div
      v-if="state.open && text"
      class="tooltip-pop"
      :class="{ below: !state.above }"
      :style="{
        top: `${state.top}px`,
        left: `${state.left}px`,
        maxWidth: `min(${maxWidth}px, 90vw)`,
      }"
      role="tooltip"
    >
      {{ text }}
    </div>
  </Teleport>
</template>

<style scoped>
.tooltip-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 10px;
  line-height: 1;
  cursor: help;
  opacity: 0.65;
  user-select: none;
}
.tooltip-trigger:hover,
.tooltip-trigger:focus-visible {
  opacity: 1;
  outline: none;
}
.tooltip-pop {
  position: fixed;
  z-index: 10080;
  box-sizing: border-box;
  padding: 6px 9px;
  border-radius: 6px;
  background: #1c1914;
  color: #fff;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-line;
  overflow-wrap: anywhere;
  pointer-events: none;
  box-shadow: 0 6px 20px rgb(0 0 0 / 20%);
  transform: translate(-50%, -100%);
}
.tooltip-pop.below {
  transform: translate(-50%, 0);
}
</style>
