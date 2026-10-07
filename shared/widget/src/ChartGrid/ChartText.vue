<script setup lang="ts">
import type { ChartGridCard } from './types'

defineProps<{ card: ChartGridCard }>()
</script>

<template>
  <div class="chart-card">
    <div class="chart-head">
      <span class="chart-title">{{ card.title }}</span>
    </div>
    <div class="chart-body">
      <pre class="chart-text">{{ card.content || '' }}</pre>
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
  padding: 8px 12px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
}
.chart-title {
  font-size: 14px;
  font-weight: 600;
}
.chart-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.chart-text {
  margin: 0;
  white-space: pre-wrap;
  font: inherit;
  color: var(--ink, #1c1914);
}
</style>
