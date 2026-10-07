<script setup lang="ts">
import { computed } from 'vue'
import { ICONS, type IconName } from './icons'

const props = withDefaults(
  defineProps<{
    name: IconName
    size?: number | string
  }>(),
  { size: 14 },
)

const marks = computed(() => ICONS[props.name])
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 16 16"
    fill="none"
    aria-hidden="true"
  >
    <template v-for="(mark, i) in marks" :key="i">
      <circle
        v-if="mark.circle"
        :cx="mark.circle.cx"
        :cy="mark.circle.cy"
        :r="mark.circle.r"
        stroke="currentColor"
        :stroke-width="mark.sw"
      />
      <path
        v-else
        :d="mark.d"
        stroke="currentColor"
        :stroke-width="mark.sw"
        :stroke-linecap="mark.cap ? 'round' : undefined"
        :stroke-linejoin="mark.join ? 'round' : undefined"
      />
    </template>
  </svg>
</template>
