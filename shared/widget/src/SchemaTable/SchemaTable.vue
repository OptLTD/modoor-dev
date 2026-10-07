<template>
  <div class="table-wrap" :class="{ 'table-wrap--toolbar-only': hideBody }">
    <div class="toolbar" :class="{ 'qf-expanded': qfOpen }">
      <div class="toolbar-left">
        <template v-if="!hideBody">
          <template v-for="(cluster, i) in api.toolbar.toolbarClusters" :key="cluster.key + '-' + i">
            <Dropdown
              v-if="cluster.group && cluster.clicks.length > 1"
              :label="clusterLabel(cluster)"
              :button-class="clickClass(cluster.clicks[0])"
            >
              <button
                v-for="c in cluster.clicks"
                :key="c.uukey"
                type="button"
                class="dropdown-item"
                role="menuitem"
                @click="onButtonClick(c)"
              >
                {{ clickLabel(c) }}
              </button>
            </Dropdown>
            <button
              v-else
              type="button"
              class="btn"
              :class="clickClass(cluster.clicks[0])"
              @click="onButtonClick(cluster.clicks[0])"
            >
              {{ clickLabel(cluster.clicks[0]) }}
            </button>
          </template>
        </template>
        <slot name="toolbar-extra" />
      </div>
      <div v-if="!hideFilter && api.filter.quickFilterGroups.length" class="qf-strip">
        <div ref="qfTrack" class="qf-track" :class="{ open: qfOpen }">
          <div
            v-for="(group, index) in api.filter.quickFilterGroups"
            :key="api.layout.fieldKey(group.field)"
            class="qf-field"
            :class="{
              'is-collapsed': !qfOpen && index >= qfFit,
              'qf-daterange': group.kind === 'daterange',
              'qf-text': group.kind === 'text',
              'qf-select': group.kind === 'select' || group.kind === 'relation',
            }"
          >
            <span class="qf-label">{{ group.field.label || group.field.field }}</span>
            <SelectBox
              v-if="group.kind === 'select'"
              bare
              searchable
              class="qf-select-ctl"
              :model-value="api.filter.quickSelectValue(group.field)"
              :options="api.filter.selectOptionsOf(group.field)"
              :placeholder="t('widget.pleaseSelect')"
              @update:model-value="(v) => api.filter.setQuickSelect(group.field, v)"
            />
            <SelectBox
              v-else-if="group.kind === 'relation'"
              bare
              searchable
              multiple
              class="qf-select-ctl qf-relation-ctl"
              :model-value="api.filter.quickRelationValue(group.field)"
              :options="api.filter.selectOptionsOf(group.field)"
              :placeholder="t('widget.pleaseSelect')"
              @update:model-value="(v) => api.filter.setQuickRelation(group.field, v)"
            />
            <input
              v-else-if="group.kind === 'text'"
              class="qf-control qf-text-input"
              type="search"
              :value="api.filter.quickTextValue(group.field)"
              :placeholder="t('widget.filterValue')"
              @change="api.filter.setQuickText(group.field, ($event.target as HTMLInputElement).value)"
              @keydown.enter.prevent="api.filter.setQuickText(group.field, ($event.target as HTMLInputElement).value)"
            />
            <DateRange
              v-else
              class="qf-daterange-ctl"
              :start="api.filter.quickRangeStart(group.field)"
              :end="api.filter.quickRangeEnd(group.field)"
              short-year
              @change="(p) => api.filter.setQuickRange(group.field, p.start, p.end)"
            />
          </div>
        </div>
        <button
          v-if="qfFit < api.filter.quickFilterGroups.length"
          type="button"
          class="icon-btn qf-more"
          :class="{ active: qfOpen }"
          :aria-expanded="qfOpen"
          :title="qfOpen ? t('widget.collapseFilters') : t('widget.expandFilters')"
          :aria-label="qfOpen ? t('widget.collapseFilters') : t('widget.expandFilters')"
          @click="qfOpen = !qfOpen"
        >
          <SvgIcon :name="qfOpen ? 'chevrons-left' : 'chevrons-right'" />
        </button>
      </div>
      <div v-show="!qfOpen" class="toolbar-right">
        <template v-if="!hidePagination">
          <div class="pager">
            <span class="muted pager-page">
              {{ api.list.page }} / {{ api.list.pages }}
            </span>
            
            <button
              type="button"
              class="icon-btn pager-nav"
              :disabled="api.list.page <= 1"
              :title="t('widget.prevPage')"
              :aria-label="t('widget.prevPage')"
              @click="api.list.goto(api.list.page - 1)"
            >
              <SvgIcon name="chevron-left" />
            </button>
            <button
              type="button"
              class="icon-btn pager-nav"
              :disabled="api.list.page >= api.list.pages"
              :title="t('widget.nextPage')"
              :aria-label="t('widget.nextPage')"
              @click="api.list.goto(api.list.page + 1)"
            >
              <SvgIcon name="chevron-right" />
            </button>
            <label class="pager-size">
              <select
                :value="api.list.size"
                :aria-label="t('widget.pageSize')"
                @change="api.list.setPageSize(Number(($event.target as HTMLSelectElement).value))"
              >
                <option v-for="n in api.list.pageSizes" :key="n" :value="n">{{ n }}</option>
              </select>
              <span class="pager-size-caret" aria-hidden="true">▾</span>
            </label>
          </div>
        </template>
        <button
          v-if="!hideBody"
          type="button"
          class="icon-btn"
          :class="{ active: api.columns.open }"
          :title="t('widget.columns')"
          :aria-pressed="api.columns.open"
          @click="api.columns.toggleOpen"
        >
          <SvgIcon name="columns" />
        </button>
        <button
          v-if="!hideFilter"
          type="button"
          class="icon-btn"
          :class="{ active: api.filter.panelFilterOpen }"
          :title="t('widget.filter')"
          @click="api.filter.togglePanelFilter"
        >
          <SvgIcon name="filter" />
          <span v-if="api.filter.activeFilterCount" class="icon-badge">{{ api.filter.activeFilterCount }}</span>
        </button>
        <button
          :title="t('widget.refresh')"
          type="button"
          class="icon-btn"
          :disabled="hideBody ? false : api.list.loading"
          @click="onRefreshClick"
        >
          <SvgIcon name="refresh" />
        </button>
      </div>
    </div>

    <div v-if="api.list.error" class="error">{{ api.list.error }}</div>

    <div v-if="!hideBody" class="table-body">
      <div v-if="!hideBody" class="scroller" :class="{ loading: api.list.loading }">
        <div class="list-frame" :class="{ 'has-totals': api.list.hasTotals }">
        <table class="list-grid">
          <thead>
            <tr>
              <th
                class="sticky-col sticky-check"
                :class="api.layout.stickyEdgeOnCheck() ? 'sticky-edge' : ''"
                :style="{
                  left: '0px',
                  width: api.layout.CHECK_W + 'px',
                  minWidth: api.layout.CHECK_W + 'px',
                  maxWidth: api.layout.CHECK_W + 'px',
                }"
              >
                <input
                  ref="checkAllRef"
                  type="checkbox"
                  :checked="api.selection.allSelected"
                  @change="api.selection.toggleAll"
                />
              </th>
            <th
              v-if="api.toolbar.actionClicks.length > 0"
              class="sticky-col sticky-action"
              :class="api.layout.stickyEdgeOnAction() ? 'sticky-edge' : ''"
              :style="{
                left: api.layout.CHECK_W + 'px',
                width: api.layout.actionWidth + 'px',
                minWidth: api.layout.actionWidth + 'px',
                maxWidth: api.layout.actionWidth + 'px',
              }"
            >
              <div class="hdr-box">
                {{ t('widget.actions') }}
                <span
                  class="col-resize"
                  @mousedown.prevent.stop="api.layout.startResize($event, api.layout.ACTION_KEY, api.layout.actionWidth, api.layout.actionResizeMin)"
                />
              </div>
            </th>
            <th
              v-for="f in api.layout.displayFields"
              :key="f.uukey"
              class="hdr-cell"
              :class="[
                api.layout.isLastStickyField(f) ? 'sticky-edge' : '',
                api.layout.isStickyField(f) ? 'sticky-col sticky-field' : '',
                api.layout.isNumericCol(f) ? 'num' : '',
              ]"
              :style="{
                width: api.layout.fieldWidth(f) + 'px',
                minWidth: api.layout.fieldWidth(f) + 'px',
                maxWidth: api.layout.fieldWidth(f) + 'px',
                left: api.layout.isStickyField(f) ? api.layout.stickyLeft(f) + 'px' : undefined,
              }"
            >
              <div class="hdr-box">
              <div class="hdr-inner">
                <span class="hdr-label truncate" :title="f.remark || f.label || f.field">
                  {{ f.label || f.field }}
                </span>
                <div class="hdr-actions">
                  <button
                    v-if="api.sort.isHeaderFilterable(f)"
                    :title="t('widget.filter')"
                    type="button"
                    class="hdr-icon"
                    :class="{
                      active: api.filter.hasFilter(f),
                      open: api.filter.filterOpen === api.layout.fieldKey(f),
                    }"
                    @click.stop="api.filter.openFilter(f)"
                  >
                    <SvgIcon name="filter" :size="12" />
                  </button>
                  <button
                    v-if="api.sort.isSortableField(f)"
                    type="button"
                    class="hdr-icon"
                    :class="api.sort.sortState(f) ? 'active' : ''"
                    :title="
                      api.sort.sortState(f) === 'asc'
                        ? t('widget.sortAsc')
                        : api.sort.sortState(f) === 'desc'
                          ? t('widget.sortDesc')
                          : t('widget.sort')
                    "
                    @click.stop="api.sort.toggleSort(f)"
                  >
                    <SvgIcon
                      :size="12"
                      :name="
                        api.sort.sortState(f) === 'asc'
                          ? 'sort-asc'
                          : api.sort.sortState(f) === 'desc'
                            ? 'sort-desc'
                            : 'sort'
                      "
                    />
                  </button>
                </div>
              </div>
              <div
                v-if="api.filter.filterOpen === api.layout.fieldKey(f)"
                class="filter-pop"
                @click.stop
              >
                <template v-if="api.filter.ftypeOf(f) === 'DATETIME'">
                  <DateRange
                    class="filter-daterange"
                    :start="api.filter.quickRangeStart(f)"
                    :end="api.filter.quickRangeEnd(f)"
                    short-year
                    @change="
                      (p) => {
                        api.filter.setQuickRange(f, p.start, p.end)
                        api.filter.closeFilter()
                      }
                    "
                  />
                  <div class="filter-actions">
                    <button type="button" class="link" @click="api.filter.clearFilter(f)">
                      {{ t('widget.clear') }}
                    </button>
                  </div>
                </template>
                <template v-else>
                <label class="filter-label">
                  {{ t('widget.condition') }}
                  <select v-model="api.filter.ensureDraft(f).op">
                    <option v-for="op in api.filter.filterOps(f)" :key="op.value" :value="op.value">
                      {{ op.label }}
                    </option>
                  </select>
                </label>
                <template v-if="api.filter.showValue(api.filter.ensureDraft(f).op)">
                  <div
                    v-if="api.filter.useFacetFilter(f)"
                    class="filter-input-wrap"
                  >
                    <SelectBox
                      searchable
                      :model-value="api.filter.multiFilterValue(f)"
                      :options="api.filter.selectOptionsOf(f)"
                      :multiple="true"
                      :placeholder="t('widget.pleaseSelect')"
                      @update:model-value="(v) => api.filter.onMultiFilterValue(f, v)"
                    />
                  </div>
                  <div
                    v-else-if="
                      (api.filter.ftypeOf(f) === 'OPTIONAL' || api.filter.ftypeOf(f) === 'RELATION') &&
                      api.filter.hasReferOptions(f)
                    "
                    class="filter-input-wrap"
                  >
                    <SelectBox
                      searchable
                      :model-value="api.filter.multiFilterValue(f)"
                      :options="api.filter.optionsOf(f)"
                      :multiple="true"
                      :placeholder="t('widget.pleaseSelect')"
                      @update:model-value="(v) => api.filter.onMultiFilterValue(f, v)"
                    />
                  </div>
                  <input
                    v-else-if="
                      api.filter.ftypeOf(f) === 'NUMERIC' ||
                      api.filter.ftypeOf(f) === 'EXPENSE' ||
                      api.filter.ftypeOf(f) === 'INTEGER'
                    "
                    v-model="api.filter.ensureDraft(f).value"
                    type="number"
                    class="filter-input"
                    :placeholder="t('widget.numberPh')"
                  />
                  <input
                    v-else
                    v-model="api.filter.ensureDraft(f).value"
                    type="text"
                    class="filter-input"
                    :placeholder="t('widget.filterValue')"
                    @keydown.enter="api.filter.applyFilter(f)"
                  />
                  <input
                    v-if="api.filter.needsValue2(api.filter.ensureDraft(f).op) && !api.filter.useFacetFilter(f)"
                    v-model="api.filter.ensureDraft(f).value2"
                    type="number"
                    class="filter-input"
                    :placeholder="t('widget.endValue')"
                  />
                </template>
                <div class="filter-actions">
                  <button type="button" class="link" @click="api.filter.clearFilter(f)">{{ t('widget.clear') }}</button>
                  <button type="button" class="link accent" @click="api.filter.applyFilter(f)">{{ t('widget.apply') }}</button>
                </div>
                </template>
              </div>
              <span
                class="col-resize"
                @mousedown.prevent.stop="api.layout.startResize($event, api.layout.fieldKey(f), api.layout.fieldWidth(f))"
              />
              </div>
            </th>
            <th class="list-fill" aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="!api.list.loading && !api.list.displayRows.length">
            <td :colspan="api.layout.displayFields.length + 3" class="empty">{{ t('widget.empty') }}</td>
          </tr>
          <tr
            v-for="(row, i) in api.list.displayRows"
            :key="api.selection.rowKey(row) || 'r-' + i"
            class="data-row"
          >
            <td
              class="sticky-col sticky-check"
              :class="api.layout.stickyEdgeOnCheck() ? 'sticky-edge' : ''"
              :style="{
                left: '0px',
                width: api.layout.CHECK_W + 'px',
                minWidth: api.layout.CHECK_W + 'px',
                maxWidth: api.layout.CHECK_W + 'px',
              }"
            >
              <input
                type="checkbox"
                :checked="api.selection.isRowSelected(row)"
                @click.stop
                @change="api.selection.toggleOne(api.selection.rowKey(row), $event)"
              />
            </td>
            <td
              v-if="api.toolbar.actionClicks.length > 0"
              class="sticky-col sticky-action"
              :class="api.layout.stickyEdgeOnAction() ? 'sticky-edge' : ''"
              :style="{
                left: api.layout.CHECK_W + 'px',
                width: api.layout.actionWidth + 'px',
                minWidth: api.layout.actionWidth + 'px',
                maxWidth: api.layout.actionWidth + 'px',
              }"
            >
              <div class="row-actions">
                <button
                  v-for="c in api.toolbar.actionClicks"
                  :key="c.uukey"
                  type="button"
                  class="link"
                  @click="onActionClick(c, row)"
                >
                  {{ c.label || c.uukey }}
                </button>
                <slot name="row-actions" :row="row" />
              </div>
            </td>
            <td
              v-for="f in api.layout.displayFields"
              :key="f.uukey"
              class="truncate"
              :class="[
                api.layout.isLastStickyField(f) ? 'sticky-edge' : '',
                api.layout.isStickyField(f) ? 'sticky-col sticky-field' : '',
                api.layout.isNumericCol(f) ? 'num' : '',
                isNavigableField(f) ? 'cell-nav' : '',
                cellTags(row, f).length ? 'tags-cell' : '',
              ]"
              :style="{
                width: api.layout.fieldWidth(f) + 'px',
                minWidth: api.layout.fieldWidth(f) + 'px',
                maxWidth: api.layout.fieldWidth(f) + 'px',
                left: api.layout.isStickyField(f) ? api.layout.stickyLeft(f) + 'px' : undefined,
              }"
              :title="cellTitle(row, f)"
              @click="isNavigableField(f) ? onCellNavigate(row, f) : undefined"
            >
              <span v-if="cellTags(row, f).length" class="cell-tags">
                <span
                  v-for="tag in cellTags(row, f)"
                  :key="tag.value"
                  class="cell-tag"
                  :title="tag.label"
                >{{ tag.short }}</span>
              </span>
              <button
                v-else-if="isNavigableField(f) && String(api.cell.displayCell(row, f) ?? '').trim()"
                type="button"
                class="cell-link"
                @click.stop="onCellNavigate(row, f)"
              >
                {{ api.cell.displayCell(row, f) }}
              </button>
              <button
                v-else-if="uploadIds(row, f).length"
                type="button"
                class="cell-link"
                @click.stop="openFiles(row, f)"
              >
                {{ t('widget.viewFiles', { n: uploadIds(row, f).length }) }}
              </button>
              <template v-else>{{ api.cell.displayCell(row, f) }}</template>
            </td>
            <td class="list-fill" aria-hidden="true" />
          </tr>
        </tbody>
      </table>

        <div v-if="api.list.hasTotals" class="list-spacer" aria-hidden="true" />

        <table v-if="api.list.hasTotals" class="list-grid list-totals">
          <tbody>
            <tr>
              <td
                class="sticky-col sticky-check muted"
                :class="api.layout.stickyEdgeOnCheck() ? 'sticky-edge' : ''"
                :style="{
                  left: '0px',
                  width: api.layout.CHECK_W + 'px',
                  minWidth: api.layout.CHECK_W + 'px',
                  maxWidth: api.layout.CHECK_W + 'px',
                }"
              >
                {{ t('widget.sum') }}
              </td>
              <td
                v-if="api.toolbar.actionClicks.length > 0"
                class="sticky-col sticky-action"
                :class="api.layout.stickyEdgeOnAction() ? 'sticky-edge' : ''"
                :style="{
                  left: api.layout.CHECK_W + 'px',
                  width: api.layout.actionWidth + 'px',
                  minWidth: api.layout.actionWidth + 'px',
                  maxWidth: api.layout.actionWidth + 'px',
                }"
              />
              <td
                v-for="f in api.layout.displayFields"
                :key="'total-' + f.uukey"
                class="truncate"
                :class="[
                  api.layout.isLastStickyField(f) ? 'sticky-edge' : '',
                  api.layout.isStickyField(f) ? 'sticky-col sticky-field' : '',
                  api.layout.isNumericCol(f) ? 'num' : '',
                ]"
                :style="{
                  width: api.layout.fieldWidth(f) + 'px',
                  minWidth: api.layout.fieldWidth(f) + 'px',
                  maxWidth: api.layout.fieldWidth(f) + 'px',
                  left: api.layout.isStickyField(f) ? api.layout.stickyLeft(f) + 'px' : undefined,
                }"
                :title="api.cell.formatTotalCell(f)"
              >
                {{ api.cell.formatTotalCell(f) }}
              </td>
              <td class="list-fill" aria-hidden="true" />
            </tr>
          </tbody>
        </table>
        </div>
      <div v-if="!hideBody && api.list.loading" class="load-mask muted">{{ t('widget.loading') }}</div>
      </div>

    </div>

    <SideDrawer
      :open="!hideFilter && api.filter.panelFilterOpen"
      :title="t('widget.filter')"
      width="360px"
      @close="api.filter.closePanelFilter"
    >
      <template #extra>
        <button
          type="button"
          class="link"
          :disabled="!filterPanelRef?.activeCount"
          @click="filterPanelRef?.resetAll()"
        >
          {{ t('widget.reset') }}
        </button>
      </template>
      <FilterPanel
        ref="filterPanelRef"
        bare
        :refers="api.list.theRefers"
        :fields="api.filter.panelFilterFields"
        :model-value="api.filter.appliedFilters"
        @reset="api.filter.clearAllFilters"
        @update="api.filter.onPanelFilters"
      />
    </SideDrawer>

    <SideDrawer
      :open="!hideBody && api.columns.open"
      :title="t('widget.columns')"
      width="320px"
      @close="api.columns.close"
    >
      <template #extra>
        <button
          type="button"
          class="link"
          :disabled="!columnPanelRef?.customized"
          @click="columnPanelRef?.reset()"
        >
          {{ t('widget.reset') }}
        </button>
      </template>
      <ColumnPanel
        ref="columnPanelRef"
        bare
        :items="api.columns.items"
        :customized="api.columns.customized"
        @move="api.columns.move"
        @reset="api.columns.reset"
        @toggle="api.columns.toggle"
      />
    </SideDrawer>
    <ImageViewer
      v-if="fileOpen"
      :items="fileItems"
      :index="fileIndex"
      @close="fileOpen = false"
      @update:index="fileIndex = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { nextTick, ref, watch } from 'vue'
import { useSchemaTable } from './useSchemaTable'
import SelectBox from '../SelectBox/SelectBox.vue'
import DateRange from '../DateRange/DateRange.vue'
import Dropdown from '../Dropdown/Dropdown.vue'
import SvgIcon from '../SvgIcon/SvgIcon.vue'
import SideDrawer from '../SideDrawer/SideDrawer.vue'
import FilterPanel from '../FilterPanel/FilterPanel.vue'
import ColumnPanel from '../ColumnPanel/ColumnPanel.vue'
import ImageViewer, { type ViewerItem } from '../ImageViewer/ImageViewer.vue'
import { assetContentUrl, fieldRefer, isMultiple, tagChips, useRecordGateway } from '@modoor/hooks'
import { pickFieldValue, rowUUKey, useI18n } from '@modoor/hooks'
import type { SchemaClick, SchemaTable, SchemaField } from '@modoor/hooks'


const props = withDefaults(
  defineProps<{
    table: SchemaTable
    using?: string
    actionMin?: number
    hideBody?: boolean
    hideFilter?: boolean
    hidePagination?: boolean
  }>(),
  {
    hideBody: false,
    hidePagination: false,
    hideFilter: false,
  },
)

const filterPanelRef = ref<{ resetAll: () => void; activeCount: number } | null>(null)
const columnPanelRef = ref<{ reset: () => void; customized: boolean } | null>(null)

const emit = defineEmits<{
  'button-click': [
    payload: { click: SchemaClick; keys: string[]; records: Record<string, unknown>[] },
  ]
  'action-click': [payload: { click: SchemaClick; record: Record<string, unknown>; key: string }]
  'record-click': [
    payload: {
      model: string
      uukey?: string
      title?: string
      field?: SchemaField
      record?: Record<string, unknown>
      lookup?: Record<string, unknown>
    },
  ]
  'request-change': [
    payload: { page: number; size: number; query?: Record<string, unknown> },
  ]
  refresh: []
}>()

const { t } = useI18n()
const gateway = useRecordGateway()
const fileOpen = ref(false)
const fileIndex = ref(0)
const fileItems = ref<ViewerItem[]>([])
const api = useSchemaTable(props, {
  onRequestChange: (req) => emit('request-change', req),
})

const checkAllRef = ref<HTMLInputElement | null>(null)
const qfTrack = ref<HTMLElement | null>(null)
const qfOpen = ref(false)
const qfFit = ref(Number.POSITIVE_INFINITY)
const qfWidths = new Map<string, number>()
let qfRightWidth = 0
let qfObserver: ResizeObserver | null = null

function measureQuickFilters() {
  const track = qfTrack.value
  const groups = api.filter.quickFilterGroups
  const count = groups.length
  if (!track || !count) {
    qfFit.value = count
    return
  }
  const toolbar = track.closest('.toolbar') as HTMLElement | null
  const left = toolbar?.querySelector('.toolbar-left') as HTMLElement | null
  const right = toolbar?.querySelector('.toolbar-right') as HTMLElement | null
  if (!toolbar || !left || !right) return
  const toolbarStyle = getComputedStyle(toolbar)
  const toolbarGap = Number.parseFloat(toolbarStyle.columnGap || '0') || 0
  const pad =
    (Number.parseFloat(toolbarStyle.paddingLeft || '0') || 0) +
    (Number.parseFloat(toolbarStyle.paddingRight || '0') || 0)
  const gap = Number.parseFloat(getComputedStyle(track).columnGap || '0') || 0
  const kids = [...track.children] as HTMLElement[]
  const keys = groups.map((group) => api.layout.fieldKey(group.field))
  kids.forEach((el, i) => {
    if (!el.classList.contains('is-collapsed')) qfWidths.set(keys[i], el.offsetWidth)
  })
  const widths = kids.map((el, i) => qfWidths.get(keys[i]) ?? el.offsetWidth)
  const fitIn = (room: number) => {
    let used = 0
    for (let i = 0; i < widths.length; i++) {
      const next = used + (i ? gap : 0) + widths[i]
      if (next > room + 1) return i
      used = next
    }
    return widths.length
  }
  if (right.offsetWidth > 0) qfRightWidth = right.offsetWidth
  const rightWidth = right.offsetWidth > 0 ? right.offsetWidth : qfRightWidth
  let room = toolbar.clientWidth - pad - left.offsetWidth - rightWidth - toolbarGap * 2
  if (room < 8) return
  let fit = fitIn(room)
  if (fit < count) {
    const more = toolbar.querySelector('.qf-more') as HTMLElement | null
    room -= (more?.offsetWidth || 32) + 8
    fit = fitIn(room)
  }
  if (fit !== qfFit.value) qfFit.value = fit
  if (fit >= count) qfOpen.value = false
}

function bindQuickFilterObserver() {
  qfObserver?.disconnect()
  const track = qfTrack.value
  if (!track || typeof ResizeObserver === 'undefined') return
  qfObserver = new ResizeObserver(() => measureQuickFilters())
  qfObserver.observe(track)
  for (const child of track.children) qfObserver.observe(child)
}
watch(() => [api.selection.allSelected, api.selection.someSelected], () => {
  if (checkAllRef.value) checkAllRef.value.indeterminate = !!api.selection.someSelected
})

function clickClass(c: SchemaClick | undefined) {
  const action = String(c?.action || '').toUpperCase()
  const uk = String(c?.uukey || '').toLowerCase()
  if (
    action === 'RECORD.CREATE' ||
    action === 'INSERT' ||
    action === 'CREATE' ||
    uk === 'create' ||
    uk === 'record.create'
  ) {
    return 'primary'
  }
  return ''
}

function clickLabel(c: SchemaClick | undefined) {
  if (!c) return ''
  return c.label || c.uukey
}

function ftypeNav(f: SchemaField) {
  return String(f.ftype || '').toUpperCase()
}

function cellTags(row: Record<string, unknown>, f: SchemaField) {
  return tagChips(row, f)
}

function cellTitle(row: Record<string, unknown>, f: SchemaField) {
  const chips = cellTags(row, f)
  if (chips.length) return chips.map((tag) => tag.label).join('、')
  if (ftypeNav(f) === 'UPLOADS') return ''
  return String(api.cell.displayCell(row, f) ?? '')
}

function uploadIds(row: Record<string, unknown>, f: SchemaField): string[] {
  if (ftypeNav(f) !== 'UPLOADS') return []
  const raw = pickFieldValue(row, f)
  if (Array.isArray(raw)) return raw.map((item) => String(item || '').trim()).filter(Boolean)
  const text = String(raw ?? '').trim()
  return text ? [text] : []
}

function fileKind(mime: string, name: string): ViewerItem['kind'] {
  const lower = name.toLowerCase()
  if (mime.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp)$/.test(lower)) return 'image'
  if (mime === 'application/pdf' || lower.endsWith('.pdf')) return 'pdf'
  return 'file'
}

async function openFiles(row: Record<string, unknown>, f: SchemaField) {
  const ids = uploadIds(row, f)
  if (!ids.length) return
  const items: ViewerItem[] = []
  for (const id of ids) {
    let name = id
    let mime = ''
    try {
      const asset = await gateway.fetchAsset(id)
      name = asset.filename || asset.title || id
      mime = asset.mime_type || ''
    } catch {
      /* 编号仍可预览 */
    }
    items.push({ src: assetContentUrl(id), name, kind: fileKind(mime, name) })
  }
  fileItems.value = items
  fileIndex.value = 0
  fileOpen.value = true
}

/** uukey 是约定字段名，SUBJECT 是约定类型，都代表这一行本身 */
function isRowField(f: SchemaField) {
  const ft = ftypeNav(f)
  return ft === 'SERIALNO' || ft === 'SUBJECT' || f.field === 'uukey'
}

function isNavigableField(f: SchemaField) {
  if (isRowField(f)) return true
  if (ftypeNav(f) === 'RELATION' && fieldRefer(f) && !isMultiple(f)) return true
  return false
}

function onCellNavigate(row: Record<string, unknown>, f: SchemaField) {
  if (!isNavigableField(f)) return
  if (isRowField(f)) {
    const uk = rowUUKey(row)
    if (!uk) return
    emit('record-click', {
      model: props.table.model,
      uukey: uk,
      title: String(f.label || uk),
      field: f,
      record: row,
    })
    return
  }
  const refer = fieldRefer(f)
  if (!refer?.using) return
  const raw = pickFieldValue(row, f)
  const val = String(raw ?? '').trim()
  if (!val) return
  emit('record-click', {
    model: refer.using,
    lookup: { [refer.keyby]: val },
    title: String(api.cell.displayCell(row, f) || val),
    field: f,
    record: row,
  })
}

function clusterLabel(cluster: { clicks: SchemaClick[]; group?: string }) {
  const g = cluster.group || ''
  if (g && g !== 'more') return g
  return t('widget.more')
}

function onActionClick(c: SchemaClick, row: Record<string, unknown>) {
  emit('action-click', { click: c, record: row, key: api.selection.rowKey(row) })
}

function onButtonClick(c: SchemaClick | undefined) {
  if (!c) return
  const keys = [...api.selection.selectedKeys]
  const selected = api.list.rows.filter((r) => keys.includes(api.selection.rowKey(r)))
  emit('button-click', { click: c, keys, records: selected })
}

function onRefreshClick() {
  if (props.hideBody) {
    emit('refresh')
    return
  }
  void api.list.reload()
}

watch(
  () => api.filter.quickFilterGroups.map((group) => api.layout.fieldKey(group.field)).join('\n'),
  () => {
    qfFit.value = Number.POSITIVE_INFINITY
    void nextTick(() => {
      bindQuickFilterObserver()
      measureQuickFilters()
    })
  },
)

onMounted(() => {
  void nextTick(() => {
    bindQuickFilterObserver()
    measureQuickFilters()
  })
})
onUnmounted(() => {
  qfObserver?.disconnect()
})

defineExpose({
  reload: api.list.reload,
  getListRequest: api.list.getListRequest,
  getSelectedRows: () => {
    const set = new Set(api.selection.selectedKeys)
    return api.list.displayRows.filter((r) => set.has(api.selection.rowKey(r)))
  },
  getSelectedKeys: () => [...api.selection.selectedKeys],
  exportByQuery: api.actions.exportByQuery,
  exportSelected: api.actions.exportSelected,
  deleteSelected: api.actions.deleteSelected,
})

</script>

<style scoped>
.table-wrap {
  min-height: 0;
}
.table-wrap--toolbar-only {
  flex: 0 0 auto;
}
.toolbar-left {
  flex: 0 0 auto;
  flex-wrap: nowrap;
  align-items: flex-start;
}
.toolbar.qf-expanded {
  flex-wrap: nowrap;
}
.toolbar-left > .btn,
.toolbar-left > .dropdown {
  flex: 0 0 auto;
  white-space: nowrap;
}
.qf-strip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
  order: 0;
}
.qf-track {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 auto;
  min-width: 0;
  flex-wrap: nowrap;
  overflow: hidden;
  padding-top: 6px;
}
.qf-track.open {
  flex-wrap: nowrap;
  overflow: hidden;
}
.qf-track > .qf-field {
  flex: 0 0 auto;
  margin-top: 0;
  max-width: 16rem;
  /* overflow: hidden; */
}
.qf-track > .qf-field.is-collapsed {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
}
.qf-more {
  flex: 0 0 auto;
  margin-top: 6px;
}
.qf-field {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  margin-top: 4px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-md);
  background: var(--panel, #fff);
  box-sizing: border-box;
}
.qf-field:focus-within {
  border-color: var(--accent, #0f6a5a);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent, #0f6a5a) 14%, transparent);
}
.qf-label {
  position: absolute;
  left: 8px;
  top: -0.55em;
  z-index: 1;
  padding: 0 4px;
  font-size: 11px;
  line-height: 1;
  color: var(--muted, #6b6458);
  background: var(--panel, #fff);
  pointer-events: none;
  white-space: nowrap;
}
.qf-select {
  width: 9rem;
  min-width: 9rem;
  max-width: 9rem;
  padding-inline: 6px 4px;
}
.qf-select-ctl {
  width: 100%;
  min-width: 0;
  max-width: 100%;
}
.qf-relation-ctl {
  width: 100%;
  min-width: 0;
  max-width: 100%;
}
.qf-control {
  min-width: 7.5rem;
  max-width: 12rem;
  height: 28px;
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: 0.85rem;
  color: inherit;
  cursor: pointer;
}
.qf-text .qf-control {
  cursor: text;
}
.qf-text-input {
  min-width: 8rem;
  max-width: 10rem;
}
.qf-daterange {
  width: max-content;
  min-width: 11.5rem;
  max-width: none;
  padding-inline: 6px 4px;
}
.qf-daterange-ctl {
  width: 100%;
  min-width: 10.5rem;
}
.table-body {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: stretch;
}
.filter-panel,
.column-panel {
  flex: 1;
  min-height: 0;
  height: auto;
}
.pager {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 4px;
}
.pager-total {
  font-size: 12px;
  white-space: nowrap;
}
.pager-page {
  font-size: 12px;
  /* min-width: 3.25rem; */
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.pager-size {
  position: relative;
  display: inline-flex;
  align-items: center;
  height: 28px;
  min-width: 3.25rem;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-sm);
  background: #fff;
  font-size: 12px;
  color: var(--ink, #1c1914);
}
.pager-size select {
  appearance: none;
  -webkit-appearance: none;
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0 18px 0 8px;
  border: 0;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
}
.pager-size-caret {
  margin-left: auto;
  padding-right: 6px;
  font-size: 0.65rem;
  line-height: 1;
  color: var(--muted, #6b6458);
  pointer-events: none;
}
.pager-nav {
  flex-shrink: 0;
}
.scroller {
  position: relative;
  overflow: auto;
  flex: 1;
  min-width: 0;
  min-height: 0;
}
.list-frame {
  display: flex;
  flex-direction: column;
  min-width: min-content;
}
.list-frame.has-totals {
  min-height: 100%;
}
.list-spacer {
  flex: 1 1 auto;
  min-height: 0;
}
.scroller.loading {
  min-height: 120px;
}
.load-mask {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--panel) 72%, transparent);
  pointer-events: none;
}

.list-grid {
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
  width: max-content;
  min-width: 100%;
  font-size: 0.9rem;
}
.list-grid th,
.list-grid td {
  border-bottom: 1px solid var(--line);
  border-right: 1px solid color-mix(in srgb, var(--line) 55%, transparent);
  padding: 8px 10px;
  text-align: left;
  background: var(--panel);
  white-space: nowrap;
  vertical-align: middle;
  box-sizing: border-box;
}
.list-grid td {
  overflow: hidden;
}
.list-grid thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  font-weight: 600;
  background: #eef1f4;
  text-align: left!important;
}
.list-grid .hdr-cell,
.list-grid .sticky-action {
  overflow: visible;
}
.list-grid .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.list-grid .empty {
  text-align: center;
  color: var(--muted);
  padding: 28px;
  border-right: none;
}
.list-grid .data-row:hover td {
  background: #f3f8f5;
}
.list-grid .data-row:hover .sticky-col {
  background: #f3f8f5;
}

.list-fill {
  width: auto;
  min-width: 0;
  padding: 0 !important;
  border-right: none !important;
  /* background: transparent !important; */
}

.list-totals {
  position: sticky;
  bottom: 0;
  z-index: 8;
  margin-top: -1px;
  flex-shrink: 0;
}
.list-totals td {
  color: var(--ink);
  border-bottom: none;
  box-shadow: 0 -1px 0 var(--line);
  font-weight: 600;
  text-align: right!important;
  font-variant-numeric: tabular-nums;
}

.sticky-col {
  position: sticky;
  background: var(--panel);
  z-index: 2;
}
.list-grid tbody td.sticky-check {
  z-index: 4;
}
.list-grid tbody td.sticky-action {
  z-index: 3;
}
.list-grid tbody td.sticky-field {
  z-index: 2;
}
.list-grid thead th.sticky-col {
  /* background: #eef1f4; */
  z-index: 8;
}
.list-grid thead th.sticky-check {
  z-index: 9;
  padding: 0;
  text-align: center!important;
}
.list-grid thead th.sticky-action {
  z-index: 9;
}
.list-grid thead th.sticky-field {
  z-index: 9;
}
.list-totals .sticky-col {
  /* background: #eef1f4; */
  z-index: 12;
}
.sticky-check {
  text-align: center;
}
.list-totals .sticky-check {
  z-index: 14;
  padding: 0;
  font-size: smaller;
  text-align: center!important;
}
.sticky-action {
  text-align: center;
}
.row-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  gap: 6px;
  align-items: center;
  justify-content: center;
}
.list-totals .sticky-action {
  z-index: 13;
}
.list-totals .sticky-field {
  z-index: 12;
}
.sticky-edge {
  box-shadow: 2px 0 0 0 var(--line);
}

.cell-tags {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}
.cell-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 0.2rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--accent, #0f6a5a) 12%, transparent);
  color: var(--accent, #0f6a5a);
  font-size: 0.72rem;
  font-weight: 650;
  line-height: 1;
}
.cell-nav {
  cursor: pointer;
}
.cell-link {
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  color: var(--accent, #0f6a5a);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cell-link:hover {
  color: color-mix(in srgb, var(--accent, #0f6a5a) 80%, #000);
}
.hdr-box {
  position: relative;
  margin: -8px -10px;
  padding: 8px 10px;
  min-height: 100%;
}
.hdr-inner {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.hdr-label {
  flex: 1;
  min-width: 0;
}
.hdr-actions {
  right: 3px;
  position: absolute;
  display: flex;
  flex-shrink: 0;
  align-items: center;
  background: #eef1f4;
}
.hdr-icon {
  display: none;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.hdr-cell:hover .hdr-icon {
  display: inline-flex;
}
.hdr-icon:hover {
  background: color-mix(in srgb, var(--line) 70%, #fff);
  color: var(--ink);
}
.hdr-icon.active,
.hdr-icon.open {
  display: inline-flex;
  color: var(--accent);
}

.col-resize {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 3px;
  z-index: 20;
  cursor: col-resize;
  touch-action: none;
}
.list-grid thead th:hover .col-resize,
.col-resize:hover, .col-resize:active {
  background: color-mix(in srgb, var(--accent) 40%, transparent);
}

.filter-pop {
  position: absolute;
  left: 0;
  top: 100%;
  z-index: 30;
  margin-top: 2px;
  width: 14rem;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.filter-pop:has(.filter-daterange) {
  width: auto;
  min-width: 14rem;
}
.filter-daterange {
  display: block;
}
.filter-label {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--muted);
}
.filter-label select,
.filter-input {
  display: block;
  width: 100%;
  margin-top: 4px;
  margin-bottom: 6px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 5px 8px;
  font: inherit;
  font-size: 12px;
  background: #fff;
}
.filter-input-wrap {
  margin-bottom: 6px;
}
.filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.link.accent {
  color: var(--accent);
  font-weight: 600;
}
</style>
