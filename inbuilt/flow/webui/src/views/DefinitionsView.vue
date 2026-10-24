<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  getInstance,
  listDefinitions,
  listInstances,
  listSchedules,
  upsertDefinition,
  upsertSchedule,
  type FlowDefinition,
  type FlowInstance,
  type FlowTask,
} from '../api/flow'
import FlowCanvas, { type FlowGraph } from './FlowCanvas.vue'

const BLANK_GRAPH: FlowGraph = {
  nodes: [
    { id: 'start', type: 'start', label: '开始', x: 48, y: 80 },
    { id: 'end', type: 'end', label: '结束', x: 280, y: 80 },
  ],
  edges: [{ from: 'start', to: 'end' }],
}

const items = ref<FlowDefinition[]>([])
const selected = ref<FlowDefinition | null>(null)
const graph = ref<FlowGraph>({ nodes: [], edges: [] })
const triggerEvent = ref('')
const error = ref('')
const msg = ref('')
const moreId = ref('')
const drawer = ref<'runs' | 'schedule' | 'info' | 'create' | ''>('')
const drawerDef = ref<FlowDefinition | null>(null)
const infoTitle = ref('')
const infoKey = ref('')
const infoStatus = ref('draft')
const keyTouched = ref(false)
const runs = ref<FlowInstance[]>([])
const runDetail = ref<{ instance: FlowInstance; logs: unknown[]; tasks: FlowTask[] } | null>(null)
const schedules = ref<Array<Record<string, unknown>>>([])
const cron = ref('0 9 * * 1-5')
const drawerError = ref('')

function asGraph(raw: unknown): FlowGraph {
  const g = (raw || {}) as { nodes?: unknown; edges?: unknown }
  return {
    nodes: Array.isArray(g.nodes) ? (g.nodes as FlowGraph['nodes']) : [],
    edges: Array.isArray(g.edges) ? (g.edges as FlowGraph['edges']) : [],
  }
}

function needsSchedule(d: FlowDefinition) {
  const trigger = d.trigger || {}
  if (trigger.cron || trigger.type === 'schedule') return true
  const nodes = ((d.graph || {}) as { nodes?: Array<{ type?: string }> }).nodes || []
  const types = new Set(nodes.map((n) => String(n.type || '')))
  const automated = ['action', 'extract', 'score', 'delay'].some((t) => types.has(t))
  if (types.has('approval') && !automated) return false
  return automated || !types.has('approval')
}

async function reload() {
  error.value = ''
  const res = await listDefinitions()
  items.value = res.items || []
}

function pick(d: FlowDefinition) {
  selected.value = d
  graph.value = asGraph(d.graph)
  triggerEvent.value = String((d.trigger || {}).event || '')
  msg.value = ''
  moreId.value = ''
}

function toggleMore(d: FlowDefinition, ev: Event) {
  ev.stopPropagation()
  moreId.value = moreId.value === d.id ? '' : d.id
}

function closeMore() {
  moreId.value = ''
}

function onDocClick() {
  moreId.value = ''
}

async function openRuns(d: FlowDefinition) {
  pick(d)
  drawerDef.value = d
  drawer.value = 'runs'
  drawerError.value = ''
  runDetail.value = null
  const res = await listInstances({ definition_key: d.key })
  runs.value = res.items || []
}

function slugKey(title: string) {
  return title
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/[^a-z0-9._-]/g, '')
}

function openCreate() {
  moreId.value = ''
  drawer.value = 'create'
  drawerDef.value = null
  infoTitle.value = ''
  infoKey.value = ''
  infoStatus.value = 'draft'
  triggerEvent.value = ''
  drawerError.value = ''
  keyTouched.value = false
  msg.value = ''
}

function onCreateTitle() {
  if (!keyTouched.value) {
    const next = slugKey(infoTitle.value)
    if (next) infoKey.value = next
  }
}

function openInfo(d: FlowDefinition) {
  pick(d)
  drawerDef.value = d
  drawer.value = 'info'
  drawerError.value = ''
  infoTitle.value = d.title || d.key
  infoKey.value = d.key
  infoStatus.value = d.status || 'draft'
  triggerEvent.value = String((d.trigger || {}).event || '')
}

async function openSchedule(d: FlowDefinition) {
  pick(d)
  drawerDef.value = d
  drawer.value = 'schedule'
  drawerError.value = ''
  const res = await listSchedules()
  schedules.value = (res.items || []).filter((s) => s.flow_key === d.key)
}

async function openRun(id: string) {
  runDetail.value = await getInstance(id)
}

async function addSchedule() {
  if (!drawerDef.value) return
  drawerError.value = ''
  try {
    await upsertSchedule({ flow_key: drawerDef.value.key, cron: cron.value, enabled: true })
    await openSchedule(drawerDef.value)
  } catch (e) {
    drawerError.value = e instanceof Error ? e.message : String(e)
  }
}

function closePanel() {
  drawer.value = ''
  drawerDef.value = null
}

async function save() {
  if (!selected.value) return
  try {
    const res = await upsertDefinition({
      definition_id: selected.value.id,
      key: selected.value.key,
      title: selected.value.title,
      status: selected.value.status,
      graph: graph.value,
      trigger: selected.value.trigger || {},
    })
    selected.value = res.definition
    graph.value = asGraph(res.definition.graph)
    msg.value = '已保存'
    await reload()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function createFlow() {
  const title = infoTitle.value.trim()
  const key = infoKey.value.trim()
  drawerError.value = ''
  if (!title || !key) {
    drawerError.value = '请填写名称和 Key'
    return
  }
  if (!/^[a-zA-Z][a-zA-Z0-9._-]*$/.test(key)) {
    drawerError.value = 'Key 需以字母开头，只能含字母、数字、点、下划线、短横线'
    return
  }
  if (items.value.some((d) => d.key === key)) {
    drawerError.value = 'Key 已存在'
    return
  }
  try {
    const res = await upsertDefinition({
      key,
      title,
      status: infoStatus.value,
      graph: BLANK_GRAPH,
      trigger: triggerEvent.value.trim() ? { event: triggerEvent.value.trim() } : {},
    })
    await reload()
    pick(res.definition)
    closePanel()
    msg.value = '已创建'
  } catch (e) {
    drawerError.value = e instanceof Error ? e.message : String(e)
  }
}

async function saveInfo() {
  const d = drawerDef.value || selected.value
  if (!d) return
  drawerError.value = ''
  try {
    const res = await upsertDefinition({
      definition_id: d.id,
      key: d.key,
      title: infoTitle.value,
      status: infoStatus.value,
      graph: selected.value?.id === d.id ? graph.value : asGraph(d.graph),
      trigger: { ...(d.trigger || {}), event: triggerEvent.value },
    })
    if (selected.value?.id === d.id) {
      selected.value = res.definition
      graph.value = asGraph(res.definition.graph)
    }
    drawerDef.value = res.definition
    msg.value = '已保存'
    await reload()
  } catch (e) {
    drawerError.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  reload()
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <section class="panel layout">
    <aside>
      <header class="aside-head">
        <div>
          <h1>流程配置</h1>
          <p class="muted">拖节点排版，右侧圆点连线</p>
        </div>
        <button type="button" class="btn primary" @click.stop="openCreate">新增</button>
      </header>
      <div
        v-for="d in items"
        :key="d.id"
        class="item"
        :class="{ on: selected?.id === d.id }"
        @click="pick(d)"
      >
        <div class="item-main">
          <strong>{{ d.title || d.key }}</strong>
          <span class="muted">{{ d.key }} · v{{ d.version }} · {{ d.status }}</span>
        </div>
        <div class="more" @click.stop>
          <button type="button" class="more-btn" title="更多" @click="toggleMore(d, $event)">⋯</button>
          <div v-if="moreId === d.id" class="more-menu" role="menu">
            <button type="button" role="menuitem" @click="openInfo(d)">流程信息</button>
            <button type="button" role="menuitem" @click="openRuns(d)">运行记录</button>
            <button v-if="needsSchedule(d)" type="button" role="menuitem" @click="openSchedule(d)">定时触发</button>
          </div>
        </div>
      </div>
    </aside>
    <main v-if="selected" class="main">
      <header class="head">
        <h2>{{ selected.title }}</h2>
        <div class="head-actions">
          <span v-if="msg" class="ok">{{ msg }}</span>
          <button type="button" class="btn primary" @click="save">保存流程图</button>
        </div>
      </header>
      <p v-if="error" class="err">{{ error }}</p>
      <FlowCanvas v-model="graph" />
    </main>
    <main v-else class="muted empty">选择一条流程开始设计，或点左侧新增</main>

    <Teleport to="body">
      <div v-if="drawer === 'info' || drawer === 'create'" class="modal-mask" @click.self="closePanel">
        <div class="modal" role="dialog" aria-modal="true">
          <header class="modal-head">
            <strong>{{ drawer === 'create' ? '新增流程' : '流程信息' }}</strong>
            <button type="button" class="btn" @click="closePanel">关闭</button>
          </header>
          <form class="form" @submit.prevent="drawer === 'create' ? createFlow() : saveInfo()">
            <label class="field">
              名称
              <input v-model="infoTitle" required @input="drawer === 'create' && onCreateTitle()" />
            </label>
            <label class="field">
              Key
              <input
                v-if="drawer === 'create'"
                v-model="infoKey"
                required
                placeholder="例如 company.cert"
                @input="keyTouched = true"
              />
              <input v-else :value="drawerDef?.key" readonly />
            </label>
            <label class="field">
              状态
              <select v-model="infoStatus">
                <option value="draft">草稿</option>
                <option value="published">已发布</option>
              </select>
            </label>
            <label class="field">
              触发事件
              <input v-model="triggerEvent" placeholder="例如 capacity.company.materials_uploaded" />
            </label>
            <p v-if="drawerError" class="err">{{ drawerError }}</p>
            <p v-if="msg" class="ok">{{ msg }}</p>
            <div class="modal-actions">
              <button type="button" class="btn" @click="closePanel">取消</button>
              <button type="submit" class="btn primary">{{ drawer === 'create' ? '创建' : '保存' }}</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <div v-if="(drawer === 'runs' || drawer === 'schedule') && drawerDef" class="drawer-mask" @click.self="closePanel">
      <aside class="drawer">
        <header class="drawer-head">
          <div>
            <h2>{{ drawer === 'runs' ? '运行记录' : '定时触发' }}</h2>
            <p class="muted">{{ drawerDef.title || drawerDef.key }}</p>
          </div>
          <button type="button" class="btn" @click="closePanel">关闭</button>
        </header>
        <template v-if="drawer === 'runs'">
          <p v-if="!runs.length" class="muted">这条流程还没有运行记录</p>
          <button
            v-for="it in runs"
            :key="it.id"
            type="button"
            class="run"
            @click="openRun(it.id)"
          >
            <strong>{{ it.status }}</strong>
            <span class="muted">{{ it.current_node }} · {{ it.id.slice(0, 8) }}</span>
          </button>
          <pre v-if="runDetail">{{ JSON.stringify(runDetail, null, 2) }}</pre>
        </template>
        <template v-else>
          <p class="muted">仅自动化 / 需要按点开工的流程才用定时。5 段 cron：分 时 日 月 周</p>
          <div class="form">
            <input v-model="cron" placeholder="0 9 * * 1-5" />
            <button type="button" class="btn primary" @click="addSchedule">添加</button>
          </div>
          <p v-if="drawerError" class="err">{{ drawerError }}</p>
          <ul>
            <li v-for="s in schedules" :key="String(s.id)">
              <code>{{ s.cron }}</code> · {{ s.enabled ? '开' : '关' }}
              · next {{ s.next_run_at || '—' }}
            </li>
          </ul>
        </template>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.aside-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}
.aside-head h1 { margin: 0 0 4px; }
.layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 16px;
  padding: 16px 20px;
  height: calc(100vh - 72px);
  min-height: calc(100vh - 72px);
  position: relative;
}
.item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  text-align: left;
  padding: 8px 6px 8px 10px;
  border-radius: 6px;
  cursor: pointer;
}
.item.on { background: #eef6f3; }
.item-main { display: grid; gap: 4px; min-width: 0; flex: 1; }
.more { position: relative; flex-shrink: 0; }
.more-btn {
  width: 26px;
  height: 26px;
  border: 0;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  color: #6b6458;
  font-size: 16px;
  line-height: 1;
}
.more-btn:hover { background: #eef1f4; }
.more-menu {
  position: absolute;
  right: 0;
  top: 28px;
  min-width: 120px;
  background: #fff;
  border: 1px solid #e2e6eb;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(28, 25, 23, 0.08);
  padding: 4px;
  z-index: 5;
}
.more-menu button {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  padding: 7px 10px;
  border-radius: 4px;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}
.more-menu button:hover { background: #eef6f3; }
.main { min-width: 0; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.head h2 { margin: 0; font-size: 1.1rem; }
.head-actions { display: flex; align-items: center; gap: 10px; }
.field {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: #6b6458;
  margin-bottom: 10px;
}
.info-form { display: grid; gap: 2px; }
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 10030;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(28, 25, 20, 0.35);
}
.modal {
  width: min(480px, 100%);
  background: #fff;
  border: 1px solid #e2e6eb;
  border-radius: 8px;
  box-shadow: 0 12px 40px rgba(40, 30, 10, 0.12);
  max-height: 90vh;
  overflow: auto;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid #e2e6eb;
}
.modal .form { padding: 16px; }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.field input,
.field select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid #d7dde3;
  border-radius: 4px;
  font: inherit;
}
.empty { display: flex; align-items: center; }
.btn { padding: 6px 12px; border-radius: 4px; border: 1px solid #d7dde3; background: #fff; cursor: pointer; }
.btn.primary { background: #0f6a5a; color: #fff; border-color: transparent; }
.err { color: #b42318; }
.ok { color: #027a48; }
.muted { color: #777; font-size: 12px; }
.drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 10020;
  display: flex;
  justify-content: flex-end;
  background: rgba(28, 25, 23, 0.18);
}
.drawer {
  width: min(420px, 100%);
  background: #fff;
  border-left: 1px solid #e2e6eb;
  padding: 16px;
  overflow: auto;
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}
.drawer-head h2 { margin: 0 0 4px; font-size: 1.05rem; }
.run {
  display: grid;
  width: 100%;
  text-align: left;
  gap: 2px;
  padding: 8px;
  border: 0;
  background: #f6f8fa;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
}
.form { display: flex; gap: 8px; margin: 10px 0; }
.form input { flex: 1; padding: 6px 8px; border: 1px solid #d7dde3; border-radius: 4px; }
pre { background: #f6f8fa; padding: 10px; border-radius: 6px; overflow: auto; font-size: 12px; }
</style>
