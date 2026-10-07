<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from '@modoor/hooks'

export type ColumnPanelItem = {
  id: string
  label: string
  visible: boolean
}

const props = withDefaults(
  defineProps<{
    items: ColumnPanelItem[]
    /** 放进抽屉时隐藏自带标题，重置按钮由外层提供 */
    bare?: boolean
    customized?: boolean
  }>(),
  { bare: false, customized: false },
)

const emit = defineEmits<{
  toggle: [id: string]
  move: [from: number, to: number]
  reset: []
}>()

const { t } = useI18n()
const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)

const visibleCount = computed(() => props.items.filter((item) => item.visible).length)

function reset() {
  emit('reset')
}

function onDragStart(index: number, e: DragEvent) {
  dragFrom.value = index
  e.dataTransfer?.setData('text/plain', String(index))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onDragOver(index: number) {
  dragOver.value = index
}

function onDrop(index: number) {
  const from = dragFrom.value
  dragFrom.value = null
  dragOver.value = null
  if (from == null || from === index) return
  emit('move', from, index)
}

function onDragEnd() {
  dragFrom.value = null
  dragOver.value = null
}

defineExpose({ reset, customized: computed(() => props.customized) })
</script>

<template>
  <div class="column-panel">
    <div v-if="!bare" class="panel-head">
      <div class="panel-title">{{ t('widget.columns') }}</div>
      <button type="button" class="link" :disabled="!customized" @click="reset">
        {{ t('widget.reset') }}
      </button>
    </div>

    <div v-if="!items.length" class="empty">{{ t('widget.empty') }}</div>
    <ul v-else class="col-list">
      <li
        v-for="(item, i) in items"
        :key="item.id"
        class="col-row"
        :class="{ 'is-over': dragOver === i && dragFrom !== i }"
        @dragover.prevent="onDragOver(i)"
        @drop.prevent="onDrop(i)"
      >
        <span
          class="col-grip"
          draggable="true"
          :title="t('widget.columnHint')"
          @dragstart="onDragStart(i, $event)"
          @dragend="onDragEnd"
        >⋮⋮</span>
        <label class="col-label">
          <input
            type="checkbox"
            :checked="item.visible"
            :disabled="item.visible && visibleCount <= 1"
            @change="emit('toggle', item.id)"
          />
          <span class="truncate" :title="item.label">{{ item.label }}</span>
        </label>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.column-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.panel-title {
  font-size: 0.875rem;
  font-weight: 600;
}
.col-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow: auto;
  flex: 1;
  min-height: 0;
}
.col-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 2px;
  border-radius: var(--radius-sm, 4px);
}
.col-row.is-over {
  background: #eef6f3;
}
.col-grip {
  flex-shrink: 0;
  width: 1rem;
  text-align: center;
  cursor: grab;
  color: var(--muted, #6b6458);
  user-select: none;
  letter-spacing: -0.12em;
  font-size: 12px;
  line-height: 1;
}
.col-label {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  flex: 1;
  font-size: 13px;
  cursor: pointer;
}
.col-label input {
  flex-shrink: 0;
}
.empty {
  padding: 24px 16px;
  text-align: center;
  color: var(--muted, #6b6458);
  font-size: 12px;
}
</style>
