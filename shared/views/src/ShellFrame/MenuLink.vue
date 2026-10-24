<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  to?: string
  moduleId: string
}>()

/** 当前应用前缀内走路由，跨到别的模块时整页打开。 */
const local = computed(() => {
  const path = String(props.to || '').trim()
  if (!path || path === '#') return true
  const base = `/mod/${props.moduleId}`
  return path === base || path.startsWith(`${base}/`)
})
</script>

<template>
  <RouterLink v-if="local" v-bind="$attrs" :to="to || '#'"><slot /></RouterLink>
  <a v-else v-bind="$attrs" :href="to || '#'"><slot /></a>
</template>
