<script setup lang="ts">
/**
 * 条件筛选抽屉（View 层）。
 */
import { ref } from 'vue'
import { useI18n, type ReferDict, type SchemaField } from '@modoor/hooks'
import type { FilterDraft } from '@modoor/hooks'
import SideDrawer from '@modoor/widget/SideDrawer'
import FilterPanel from '@modoor/widget/FilterPanel'

defineProps<{
  open: boolean
  fields: SchemaField[]
  modelValue: Record<string, FilterDraft>
  refers?: ReferDict
}>()

const emit = defineEmits<{
  close: []
  reset: []
  update: [Record<string, FilterDraft>]
}>()

const { t } = useI18n()
const filterAutoApply = ref(false)
const filterPanelRef = ref<{
  resetAll: () => void
  apply: () => void
  activeCount: number
  dirty: boolean
} | null>(null)
</script>

<template>
  <SideDrawer
    :open="open"
    :title="t('widget.filter')"
    width="360px"
    @close="emit('close')"
  >
    <FilterPanel
      ref="filterPanelRef"
      bare
      :auto-apply="filterAutoApply"
      :refers="refers"
      :fields="fields"
      :model-value="modelValue"
      @reset="emit('reset')"
      @update="emit('update', $event)"
    />
    <template #footer>
      <div class="sd-foot-left">
        <button
          type="button"
          class="link"
          :disabled="!filterPanelRef?.activeCount && !filterPanelRef?.dirty"
          @click="filterPanelRef?.resetAll()"
        >
          {{ t('widget.reset') }}
        </button>
        <label class="sd-auto">
          <input v-model="filterAutoApply" type="checkbox" />
          <span>{{ t('widget.autoApply') }}</span>
        </label>
      </div>
      <button
        type="button"
        class="btn primary"
        :disabled="!filterPanelRef?.dirty"
        @click="filterPanelRef?.apply()"
      >
        {{ t('widget.apply') }}
      </button>
    </template>
  </SideDrawer>
</template>

<style scoped>
.sd-foot-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.sd-auto {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--muted, #6b6458);
  cursor: pointer;
  user-select: none;
}
.sd-auto input {
  margin: 0;
}
</style>
