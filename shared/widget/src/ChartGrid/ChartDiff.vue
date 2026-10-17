<script setup lang="ts">
import type { ChartGridCard } from './types'

defineProps<{ card: ChartGridCard }>()

const emit = defineEmits<{
  refresh: []
  open: []
  scope: [scope: string]
}>()

const scopes = [
  { id: 'current', label: '本期' },
  { id: 'previous', label: '上期' },
  { id: 'earlier', label: '前期' },
]

function money(n: number | null | undefined) {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="chart-card diff-card" :class="{ warn: Math.abs(card.total || 0) >= 0.01 }">
    <div class="chart-head">
      <span class="chart-title">
        {{ card.title }}
        <span v-if="card.help" class="chart-help" tabindex="0" @click.stop>
          ?
          <span class="chart-help-pop" role="tooltip">{{ card.help }}</span>
        </span>
      </span>
      <div class="diff-scopes" role="tablist">
        <button
          v-for="item in scopes"
          :key="item.id"
          type="button"
          class="diff-scope"
          :class="{ active: (card.scope || 'current') === item.id }"
          @click.stop="emit('scope', item.id)"
        >
          {{ item.label }}
        </button>
      </div>
      <button type="button" class="chart-refresh" :disabled="card.loading" @click.stop="emit('refresh')">
        刷新
      </button>
    </div>
    <div class="diff-body" :class="{ clickable: card.clickable }" @click="emit('open')">
      <p v-if="card.error" class="error">{{ card.error }}</p>
      <p v-else-if="card.loading && card.total == null" class="muted">…</p>
      <div v-else class="diff-copy">
        <p class="diff-sum">
          <span class="num">{{ money(card.total) }}</span>
          <span class="affix">{{ card.suffix || '元' }}</span>
        </p>
        <p v-if="card.uterm" class="diff-note">{{ card.uterm }} 期<span v-if="card.note"> · {{ card.note }}</span></p>
        <p class="diff-parts">
          {{ card.leftLabel || '左' }} {{ money(card.left) }} − {{ card.rightLabel || '右' }} {{ money(card.right) }}
        </p>
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
.diff-card.warn {
  border-color: color-mix(in srgb, var(--danger, #a33b2b) 35%, var(--line, #e2e6eb));
}
.diff-card:hover,
.diff-card:focus-within {
  position: relative;
  z-index: 4;
}
.chart-head {
  display: flex;
  align-items: center;
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
  max-width: 260px;
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
.diff-scopes {
  display: flex;
  gap: 2px;
  margin-left: auto;
  flex-shrink: 0;
}
.diff-scope {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 2px 8px;
  border-radius: 999px;
  font: inherit;
  font-size: 12px;
  color: var(--muted, #6b6458);
  cursor: pointer;
}
.diff-scope.active {
  background: color-mix(in srgb, var(--ink, #1c1914) 8%, transparent);
  color: var(--ink, #1c1914);
  font-weight: 650;
}
.diff-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  padding: 8px 12px 12px;
}
.diff-body.clickable {
  cursor: pointer;
}
.diff-copy {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
  text-align: center;
}
.diff-sum,
.diff-note,
.diff-parts {
  margin: 0;
  line-height: 1.35;
}
.diff-sum {
  display: flex;
  align-items: baseline;
  gap: 2px;
  font-weight: 650;
  color: var(--accent, #0f6a5a);
}
.diff-sum .num {
  font-size: 28px;
  line-height: 1;
}
.diff-sum .affix {
  font-size: 13px;
}
.diff-card.warn .diff-sum {
  color: var(--danger, #a33b2b);
}
.diff-note {
  font-size: 13px;
  color: var(--ink, #1c1914);
}
.diff-parts {
  font-size: 12px;
  color: var(--muted, #6b6458);
}
.muted,
.error {
  padding: 8px;
  text-align: center;
}
.muted {
  color: var(--muted, #6b6458);
}
.error {
  color: var(--danger, #a33b2b);
  font-size: 13px;
}
</style>
