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
      <span class="chart-title">
        {{ card.title }}
        <span v-if="card.help" class="chart-help" tabindex="0" @click.stop>
          ?
          <span class="chart-help-pop" role="tooltip">{{ card.help }}</span>
        </span>
      </span>
      <button type="button" class="chart-refresh" :disabled="card.loading" @click.stop="emit('refresh')">
        刷新
      </button>
    </div>
    <div class="count-body">
      <p v-if="card.error" class="error">{{ card.error }}</p>
      <p v-else-if="card.loading && card.total == null" class="muted">…</p>
      <div v-else class="count-copy">
        <p class="count-sum">
          <span class="affix">共</span>
          <span class="num">{{ card.total ?? '—' }}</span>
          <span class="affix">{{ card.suffix || '条' }}</span>
        </p>
        <p v-if="card.note" class="count-note">{{ card.note }}</p>
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
  overflow: visible;
}
.count-card.clickable {
  cursor: pointer;
}
.count-card:hover,
.count-card:focus-within {
  position: relative;
  z-index: 4;
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
}
.chart-help {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 50%;
  color: var(--muted, #6b6458);
  font-size: 11px;
  font-weight: 650;
  line-height: 1;
  cursor: help;
  flex-shrink: 0;
}
.chart-help-pop {
  display: none;
  position: absolute;
  z-index: 8;
  top: calc(100% + 6px);
  left: 0;
  width: max-content;
  max-width: 240px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--ink, #1c1914);
  color: #fff;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.45;
  text-align: left;
  white-space: normal;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
}
.chart-help:hover .chart-help-pop,
.chart-help:focus-visible .chart-help-pop {
  display: block;
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
  padding: 12px 14px;
}
.count-copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
  text-align: center;
}
.count-sum,
.count-note {
  margin: 0;
  line-height: 1.4;
}
.count-sum {
  display: flex;
  align-items: baseline;
  gap: 2px;
  font-weight: 650;
  color: var(--accent, #0f6a5a);
}
.count-sum .num {
  font-size: 36px;
  line-height: 1;
}
.count-sum .affix {
  font-size: 14px;
}
.count-card.warn .count-sum {
  color: var(--danger, #a33b2b);
}
.count-note {
  font-size: 13px;
  color: var(--ink, #1c1914);
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
