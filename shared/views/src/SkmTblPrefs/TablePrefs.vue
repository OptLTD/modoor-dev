<script setup lang="ts">
/**
 * 列表字段 | 快捷筛选 配置抽屉（View 层）。
 */
import { useI18n } from '@modoor/hooks'
import SideDrawer from '@modoor/widget/SideDrawer'
import FieldPanel from '@modoor/widget/FieldPanel'
import type { TablePrefsApi } from './useTablePrefs'

withDefaults(
  defineProps<{
    prefs: TablePrefsApi
    /** 无快捷筛选能力时只显示列表字段 */
    hideFilter?: boolean
  }>(),
  { hideFilter: false },
)

const { t } = useI18n()
</script>

<template>
  <SideDrawer
    :open="prefs.open"
    :title="
      hideFilter
        ? t('widget.columns')
        : prefs.tab === 'filters'
          ? t('widget.quickFilters')
          : t('widget.listFields')
    "
    width="320px"
    @close="prefs.close"
  >
    <template v-if="!hideFilter" #title>
      <div class="col-tabs" role="tablist">
        <button
          type="button"
          class="col-tab"
          role="tab"
          :class="{ active: prefs.tab === 'columns' }"
          :aria-selected="prefs.tab === 'columns'"
          @click="prefs.tab = 'columns'"
        >
          {{ t('widget.listFields') }}
        </button>
        <button
          type="button"
          class="col-tab"
          role="tab"
          :class="{ active: prefs.tab === 'filters' }"
          :aria-selected="prefs.tab === 'filters'"
          @click="prefs.tab = 'filters'"
        >
          {{ t('widget.quickFilters') }}
        </button>
      </div>
    </template>
    <div class="col-tab-body">
      <FieldPanel
        v-show="hideFilter || prefs.tab === 'columns'"
        bare
        :items="prefs.columnItems"
        :customized="prefs.columnsCustomized"
        @move="prefs.moveColumn"
        @reset="prefs.resetColumns"
        @toggle="prefs.toggleColumn"
      />
      <FieldPanel
        v-show="!hideFilter && prefs.tab === 'filters'"
        bare
        :min-visible="0"
        :items="prefs.filterItems"
        :customized="prefs.filtersCustomized"
        @move="prefs.moveFilter"
        @reset="prefs.resetFilters"
        @toggle="prefs.toggleFilter"
      />
    </div>
    <template #footer>
      <button
        type="button"
        class="link"
        :disabled="prefs.tab === 'filters' ? !prefs.filtersCustomized : !prefs.columnsCustomized"
        @click="prefs.tab === 'filters' ? prefs.resetFilters() : prefs.resetColumns()"
      >
        {{ t('widget.reset') }}
      </button>
      <button
        type="button"
        class="btn primary"
        :disabled="prefs.tab === 'filters' ? !prefs.filtersDirty : !prefs.columnsDirty"
        @click="prefs.tab === 'filters' ? prefs.applyFilters() : prefs.applyColumns()"
      >
        {{ t('widget.apply') }}
      </button>
    </template>
  </SideDrawer>
</template>

<style scoped>
.col-tabs {
  display: flex;
  gap: 0;
  align-self: stretch;
  min-width: 0;
}
.col-tab {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 14px 12px 12px;
  margin-bottom: -1px;
  font: inherit;
  font-size: 0.95rem;
  color: var(--muted, #6b6458);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}
.col-tab.active {
  color: var(--ink, #1c1914);
  font-weight: 600;
  border-bottom-color: var(--ink, #1c1914);
}
.col-tab-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
