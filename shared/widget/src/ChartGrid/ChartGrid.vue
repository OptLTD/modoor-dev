<script setup lang="ts">
import ChartCount from './ChartCount.vue'
import ChartTable from './ChartTable.vue'
import ChartText from './ChartText.vue'
import type { ChartGridCard, ChartGridTab } from './types'

withDefaults(
  defineProps<{
    title?: string
    tabs?: ChartGridTab[]
    active?: string
    brief?: string
    cards?: ChartGridCard[]
  }>(),
  { title: '', tabs: () => [], active: '', brief: '', cards: () => [] },
)

const emit = defineEmits<{
  'update:active': [id: string]
  refresh: [key: string]
  open: [key: string]
  row: [payload: { key: string; rowKey: string }]
}>()
</script>

<template>
  <section class="workspace chart-grid">
    <div v-if="title || tabs.length > 1" class="ws-head">
      <div class="ws-title-row">
        <div class="ws-title-block">
          <h1 v-if="title">{{ title }}</h1>
          <nav v-if="tabs.length > 1" class="ws-tabs" aria-label="kanban">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              class="ws-tab"
              :class="{ active: active === tab.id }"
              @click="emit('update:active', tab.id)"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>
      </div>
    </div>
    <p v-if="brief" class="kanban-brief muted">{{ brief }}</p>
    <div class="kanban-grid">
      <div v-for="card in cards" :key="card.key" class="kanban-slot" :style="card.style">
        <ChartTable
          v-if="card.type === 'table'"
          :card="card"
          @refresh="emit('refresh', card.key)"
          @row="emit('row', { key: card.key, rowKey: $event })"
        />
        <ChartText v-else-if="card.type === 'text'" :card="card" />
        <ChartCount
          v-else-if="card.type === 'count'"
          :card="card"
          @refresh="emit('refresh', card.key)"
          @open="emit('open', card.key)"
        />
        <div v-else class="kanban-unsupported">{{ card.type }} 尚未接入</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chart-grid {
  overflow: auto;
}
.ws-head {
  padding-bottom: 0;
  border-bottom: 1px solid var(--line, #e2e6eb);
}
.ws-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}
.ws-title-block {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  gap: 0.75rem;
  min-width: 0;
  flex-wrap: wrap;
}
.ws-title-block h1 {
  margin: 0;
  padding-bottom: 0.5rem;
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.2;
}
.ws-tabs {
  display: flex;
  gap: 0;
  flex-wrap: wrap;
}
.ws-tab {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0.5rem 0.85rem;
  margin-bottom: -1px;
  font: inherit;
  font-size: 0.95rem;
  color: var(--muted, #6b6458);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.ws-tab.active {
  color: var(--ink, #1c1914);
  font-weight: 600;
  border-bottom-color: var(--ink, #1c1914);
}
.kanban-brief {
  margin: 0;
  padding: 10px 16px 0;
  font-size: 13px;
}
.kanban-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-auto-rows: 72px;
  gap: 12px;
  padding: 12px 16px 24px;
  align-items: stretch;
}
.kanban-slot {
  min-width: 0;
  min-height: 0;
}
.kanban-unsupported {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--line, #e2e6eb);
  border-radius: 8px;
  color: var(--muted, #6b6458);
  font-size: 13px;
}
.muted {
  color: var(--muted, #6b6458);
}
@media (max-width: 960px) {
  .kanban-grid {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(160px, auto);
  }
  .kanban-slot {
    grid-column: 1 / -1 !important;
    grid-row: auto !important;
  }
}
</style>
