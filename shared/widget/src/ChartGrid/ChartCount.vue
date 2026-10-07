<script setup lang="ts">
import type { ChartGridCard } from './types'

defineProps<{ card: ChartGridCard }>()

const emit = defineEmits<{
  refresh: []
  open: []
}>()
</script>

<template>
  <div
    class="chart-card count-card"
    :class="{ warn: (card.total || 0) > 0, clickable: card.clickable }"
    @click="emit('open')"
  >
    <div class="chart-head">
      <span class="chart-title">{{ card.title }}</span>
      <button type="button" class="chart-refresh" :disabled="card.loading" @click.stop="emit('refresh')">
        刷新
      </button>
    </div>
    <div class="count-body">
      <p v-if="card.error" class="error">{{ card.error }}</p>
      <p v-else-if="card.loading && card.total == null" class="muted">…</p>
      <div v-else class="count-value">
        <span v-if="card.prefix" class="affix">{{ card.prefix }}</span>
        <span class="num">{{ card.total ?? '—' }}</span>
        <span v-if="card.suffix" class="affix">{{ card.suffix }}</span>
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
.count-card.clickable {
  cursor: pointer;
}
.count-card.warn {
  border-color: color-mix(in srgb, var(--danger, #a33b2b) 35%, var(--line, #e2e6eb));
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
.count-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.count-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
  line-height: 1.2;
}
.num {
  font-size: 36px;
  font-weight: 650;
  color: var(--accent, #0f6a5a);
}
.count-card.warn .num {
  color: var(--danger, #a33b2b);
}
.affix {
  font-size: 13px;
  color: var(--muted, #6b6458);
}
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
