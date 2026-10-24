<template>
  <div>
    <div
      class="org-item"
      :class="{ active: activeId === node.id }"
      :style="{ paddingLeft: `${8 + depth * 12}px` }"
      @click="$emit('select', node.id)"
    >
      <button
        v-if="node.children?.length"
        type="button"
        class="twist"
        @click.stop="open = !open"
      >
        {{ open ? '▾' : '▸' }}
      </button>
      <span v-else class="twist muted">·</span>
      <span class="title">{{ node.name }}</span>
      <button type="button" class="ghost" :title="t('base.rename')" @click.stop="$emit('rename', node)">✎</button>
      <button
        v-if="node.parent != null"
        type="button"
        class="ghost danger"
        :title="t('base.delete')"
        @click.stop="$emit('remove', node)"
      >×</button>
    </div>
    <div v-if="open && node.children?.length">
      <OrgTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :active-id="activeId"
        @select="$emit('select', $event)"
        @rename="$emit('rename', $event)"
        @remove="$emit('remove', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from '@modoor/hooks'
import type { TeamNode } from '../api/base'

defineProps<{
  node: TeamNode
  depth: number
  activeId: number | null
}>()

defineEmits<{
  select: [id: number]
  rename: [node: TeamNode]
  remove: [node: TeamNode]
}>()

const { t } = useI18n()
const open = ref(true)
</script>

<style scoped>
.org-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: var(--radius-md);
  padding: 4px 6px;
  cursor: pointer;
  user-select: none;
}

.org-item:hover {
  background: #00000008;
}

.org-item.active {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
}

.title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.92rem;
}

.twist {
  border: 0;
  background: transparent;
  width: 1.2rem;
  cursor: pointer;
  font: inherit;
  color: inherit;
  padding: 0;
}

.ghost {
  border: 0;
  background: transparent;
  cursor: pointer;
  opacity: 0;
  padding: 2px 4px;
  font: inherit;
  color: var(--muted);
}

.org-item:hover .ghost {
  opacity: 1;
}

.ghost.danger {
  color: var(--danger);
}

.muted {
  color: var(--muted);
}
</style>
