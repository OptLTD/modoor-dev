<script setup lang="ts">
/**
 * 右侧抽屉壳：遮罩 + 面板 + 关闭；中间内容由 slot / 模块组件决定。
 * 传入 model + uukey（或子组件 resolve 后 inject 回传）时，header 提供「详情 / 修改记录」。
 */
import { computed, provide, ref, watch } from 'vue'
import { useI18n } from '@modoor/hooks'
import RecordOpLog from './RecordOpLog.vue'
import { RECORD_DRAWER_OPLOG_KEY } from './oplogContext'

const props = withDefaults(
  defineProps<{
    open: boolean
    title?: string
    /** 主数据卡片等较宽内容 */
    wide?: boolean
    /** 叠在 TableDrawer 之上（同级 z-index 时会被挡住） */
    elevated?: boolean
    /** 业务模型；与 uukey 一起用于修改记录 */
    model?: string
    /** 业务编号（uukey / code） */
    uukey?: string
    /** 强制开关修改记录页签；默认在 model+uukey 时开启 */
    changelog?: boolean
  }>(),
  {
    title: '',
    wide: false,
    elevated: false,
    model: '',
    uukey: '',
    changelog: undefined,
  },
)

const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

type Panel = 'detail' | 'changelog'
const activePanel = ref<Panel>('detail')

/** Props 优先；子组件（FlatDetail / RecordEntity）lookup 解析后可回填 */
const resolvedModel = ref('')
const resolvedUukey = ref('')

function syncFromProps() {
  resolvedModel.value = String(props.model || '').trim()
  resolvedUukey.value = String(props.uukey || '').trim()
}

provide(RECORD_DRAWER_OPLOG_KEY, {
  setTarget(model: string, uukey: string) {
    const m = String(model || '').trim()
    const u = String(uukey || '').trim()
    if (!m || !u) return
    // Props 已给全量时不覆盖；否则接受子组件解析结果
    if (!props.model) resolvedModel.value = m
    else resolvedModel.value = String(props.model).trim()
    if (!props.uukey) resolvedUukey.value = u
    else resolvedUukey.value = String(props.uukey).trim()
  },
  clearTarget() {
    if (!props.model) resolvedModel.value = ''
    if (!props.uukey) resolvedUukey.value = ''
  },
})

const showChangelog = computed(() => {
  const model = resolvedModel.value || String(props.model || '').trim()
  const uukey = resolvedUukey.value || String(props.uukey || '').trim()
  if (props.changelog === false) return false
  if (props.changelog === true) return Boolean(model && uukey)
  return Boolean(model && uukey && model !== 'base.oplog')
})

const oplogModel = computed(
  () => resolvedModel.value || String(props.model || '').trim(),
)
const oplogUukey = computed(
  () => resolvedUukey.value || String(props.uukey || '').trim(),
)

watch(
  () => [props.open, props.model, props.uukey] as const,
  ([open]) => {
    syncFromProps()
    if (open) activePanel.value = 'detail'
  },
  { immediate: true },
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="record-drawer-mask"
      :class="{ 'is-elevated': elevated }"
      @click.self="emit('close')"
    >
      <aside
        class="record-drawer"
        :class="{ 'is-wide': wide }"
        role="dialog"
        aria-modal="true"
        :aria-label="title || t('widget.detail')"
      >
        <header class="rd-chrome">
          <div class="rd-chrome-main">
            <strong class="rd-chrome-title truncate">{{ title }}</strong>
            <nav v-if="showChangelog" class="rd-tabs" aria-label="detail panels">
              <button
                type="button"
                role="tab"
                class="rd-tab"
                :class="{ 'is-active': activePanel === 'detail' }"
                :aria-selected="activePanel === 'detail'"
                @click="activePanel = 'detail'"
              >
                {{ t('widget.detail') }}
              </button>
              <span class="rd-tab-sep" aria-hidden="true">·</span>
              <button
                type="button"
                role="tab"
                class="rd-tab"
                :class="{ 'is-active': activePanel === 'changelog' }"
                :aria-selected="activePanel === 'changelog'"
                @click="activePanel = 'changelog'"
              >
                {{ t('widget.changelog') }}
              </button>
            </nav>
          </div>
          <button type="button" class="link" @click="emit('close')">
            {{ t('widget.close') }}
          </button>
        </header>
        <div class="rd-body">
          <div v-show="!showChangelog || activePanel === 'detail'" class="rd-panel">
            <slot />
          </div>
          <RecordOpLog
            v-if="showChangelog && activePanel === 'changelog'"
            :model="oplogModel"
            :uukey="oplogUukey"
          />
        </div>
        <footer v-if="$slots.footer && (!showChangelog || activePanel === 'detail')" class="rd-foot">
          <slot name="footer" />
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.record-drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 10085;
  background: color-mix(in srgb, var(--ink, #1c1914) 28%, transparent);
  display: flex;
  justify-content: flex-end;
}
.record-drawer-mask.is-elevated {
  z-index: 10086;
}
.record-drawer {
  width: min(420px, 100vw);
  height: 100%;
  background: var(--panel, #fff);
  border-left: 1px solid var(--line, #e2e6eb);
  box-shadow: -8px 0 24px rgba(28, 25, 23, 0.12);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.record-drawer.is-wide {
  width: min(560px, 100vw);
}
.rd-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
  min-height: 48px;
}
.rd-chrome-main {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 12px;
  min-width: 0;
  flex: 1;
}
.rd-chrome-title {
  font-size: 0.95rem;
  min-width: 0;
}
.rd-tabs {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.rd-tab {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  color: var(--muted, #6b7280);
  cursor: pointer;
}
.rd-tab:hover {
  color: var(--ink, #1c1914);
}
.rd-tab.is-active {
  color: var(--ink, #1c1914);
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.rd-tab-sep {
  color: var(--muted, #6b7280);
  font-size: 13px;
  user-select: none;
}
.rd-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  container-type: inline-size;
  container-name: rd-drawer;
}
.rd-panel {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.rd-foot {
  flex-shrink: 0;
  border-top: 1px solid var(--line, #e2e6eb);
  padding: 12px 16px;
  background: var(--panel, #fff);
}
.link {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--ink, #1c1914);
  text-decoration: underline;
  cursor: pointer;
  font-size: 13px;
  flex-shrink: 0;
}
</style>
