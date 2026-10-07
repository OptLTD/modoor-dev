<script setup lang="ts">
import type { ChartGridCard } from './types'

defineProps<{ card: ChartGridCard }>()

const emit = defineEmits<{
  refresh: []
  row: [rowKey: string]
}>()
</script>

<template>
  <div class="chart-card">
    <div class="chart-head">
      <span class="chart-title">{{ card.title }}</span>
      <button type="button" class="chart-refresh" :disabled="card.loading" @click="emit('refresh')">
        刷新
      </button>
    </div>
    <div class="chart-body">
      <p v-if="card.error" class="error">{{ card.error }}</p>
      <p v-else-if="card.loading" class="muted">加载中…</p>
      <div v-else class="chart-table-wrap">
        <table class="chart-table">
          <thead>
            <tr>
              <th v-for="col in card.columns || []" :key="col.key">{{ col.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in card.rows || []" :key="row.key" @click="emit('row', row.uukey || '')">
              <td v-for="(cell, i) in row.cells" :key="i">{{ cell || '—' }}</td>
            </tr>
            <tr v-if="!(card.rows || []).length">
              <td :colspan="Math.max((card.columns || []).length, 1)" class="empty">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: var(--panel, #fff);
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  overflow: hidden;
}
.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
}
.chart-refresh {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--muted, #6b6458);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.chart-refresh:disabled {
  opacity: 0.5;
}
.chart-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.chart-table-wrap {
  min-width: 100%;
}
.chart-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.chart-table th,
.chart-table td {
  border-bottom: 1px solid var(--line, #ebe4d8);
  padding: 6px 8px;
  text-align: left;
  white-space: nowrap;
}
.chart-table th {
  position: sticky;
  top: 0;
  background: #faf8f5;
  font-weight: 600;
  color: var(--muted, #6b6458);
}
.chart-table tbody tr {
  cursor: pointer;
}
.chart-table tbody tr:hover {
  background: color-mix(in srgb, var(--accent, #0f6a5a) 6%, #fff);
}
.empty,
.muted,
.error {
  padding: 16px;
  text-align: center;
}
.muted {
  color: var(--muted, #6b6458);
}
.error {
  color: var(--danger, #a33b2b);
}
</style>
