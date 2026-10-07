<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

export type GraphNode = {
  id: string
  type: string
  label?: string
  config?: Record<string, unknown>
  x?: number
  y?: number
}

export type GraphEdge = {
  from: string
  to: string
  when?: string
}

export type FlowGraph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

const props = defineProps<{
  modelValue: FlowGraph
}>()

const emit = defineEmits<{
  'update:modelValue': [value: FlowGraph]
}>()

const NODE_W = 168
const NODE_H = 62
const MIN_ZOOM = 0.25
const MAX_ZOOM = 2.2
const TYPES = [
  { id: 'start', label: '开始' },
  { id: 'end', label: '结束' },
  { id: 'action', label: '动作' },
  { id: 'condition', label: '条件' },
  { id: 'approval', label: '审批' },
  { id: 'extract', label: '解析' },
  { id: 'score', label: '评分' },
  { id: 'delay', label: '等待' },
]

const selectedId = ref('')
const linkingFrom = ref('')
const linkHoverId = ref('')
const viewportEl = ref<HTMLElement | null>(null)
const zoom = ref(1)
const panX = ref(24)
const panY = ref(24)
const drag = ref<
  | { kind: 'node'; id: string; dx: number; dy: number; sx: number; sy: number; moved: boolean }
  | { kind: 'pan'; x: number; y: number; ox: number; oy: number }
  | { kind: 'link'; from: string; x: number; y: number }
  | null
>(null)

const nodes = computed(() => props.modelValue?.nodes || [])
const edges = computed(() => props.modelValue?.edges || [])
const selected = computed(() => nodes.value.find((n) => n.id === selectedId.value) || null)
const zoomLabel = computed(() => `${Math.round(zoom.value * 100)}%`)

function typeLabel(type: string) {
  return TYPES.find((t) => t.id === type)?.label || type
}

function commit(next: FlowGraph) {
  emit('update:modelValue', next)
}

function patchNode(id: string, patch: Partial<GraphNode>) {
  commit({
    nodes: nodes.value.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    edges: edges.value,
  })
}

function clampZoom(v: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v))
}

function worldPoint(ev: PointerEvent | WheelEvent) {
  const el = viewportEl.value
  if (!el) return { x: 0, y: 0 }
  const r = el.getBoundingClientRect()
  return {
    x: (ev.clientX - r.left - panX.value) / zoom.value,
    y: (ev.clientY - r.top - panY.value) / zoom.value,
  }
}

function setZoomAt(next: number, cx: number, cy: number) {
  const z = clampZoom(next)
  const worldX = (cx - panX.value) / zoom.value
  const worldY = (cy - panY.value) / zoom.value
  zoom.value = z
  panX.value = cx - worldX * z
  panY.value = cy - worldY * z
}

function zoomBy(factor: number) {
  const el = viewportEl.value
  if (!el) {
    zoom.value = clampZoom(zoom.value * factor)
    return
  }
  setZoomAt(zoom.value * factor, el.clientWidth / 2, el.clientHeight / 2)
}

function contentBox() {
  if (!nodes.value.length) return { minX: 0, minY: 0, w: 400, h: 240 }
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes.value) {
    const x = n.x || 0
    const y = n.y || 0
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x + NODE_W)
    maxY = Math.max(maxY, y + NODE_H)
  }
  return { minX, minY, w: Math.max(1, maxX - minX), h: Math.max(1, maxY - minY) }
}

function fitAll(force = false) {
  const el = viewportEl.value
  if (!el || !nodes.value.length) return false
  if (el.clientWidth < 80 || el.clientHeight < 80) return false
  const box = contentBox()
  const pad = 48
  const zx = (el.clientWidth - pad * 2) / box.w
  const zy = (el.clientHeight - pad * 2) / box.h
  let next = Math.min(zx, zy, 1)
  if (!force && next < 0.55) {
    zoom.value = 1
    panX.value = 24 - box.minX
    panY.value = 24 - box.minY
    return true
  }
  zoom.value = clampZoom(next)
  panX.value = (el.clientWidth - box.w * zoom.value) / 2 - box.minX * zoom.value
  panY.value = (el.clientHeight - box.h * zoom.value) / 2 - box.minY * zoom.value
  return true
}

function resetView() {
  zoom.value = 1
  panX.value = 24
  panY.value = 24
}

function ensureLayout() {
  const list = nodes.value
  if (!list.length) return false
  const missing = list.some((n) => typeof n.x !== 'number' || typeof n.y !== 'number')
  if (!missing) return false
  const outgoing = new Map<string, string[]>()
  for (const n of list) outgoing.set(n.id, [])
  for (const e of edges.value) outgoing.get(e.from)?.push(e.to)
  const start = list.find((n) => n.type === 'start')?.id || list[0].id
  const depth = new Map<string, number>()
  const q = [start]
  depth.set(start, 0)
  while (q.length) {
    const cur = q.shift() as string
    const d = depth.get(cur) || 0
    for (const nxt of outgoing.get(cur) || []) {
      if (!depth.has(nxt)) {
        depth.set(nxt, d + 1)
        q.push(nxt)
      }
    }
  }
  for (const n of list) {
    if (!depth.has(n.id)) depth.set(n.id, 0)
  }
  const layers = new Map<number, string[]>()
  for (const n of list) {
    const d = depth.get(n.id) || 0
    const row = layers.get(d) || []
    row.push(n.id)
    layers.set(d, row)
  }
  commit({
    nodes: list.map((n) => {
      const d = depth.get(n.id) || 0
      const row = layers.get(d) || []
      return { ...n, x: 32 + d * 220, y: 36 + row.indexOf(n.id) * 92 }
    }),
    edges: edges.value,
  })
  return true
}

const graphKey = computed(() => nodes.value.map((n) => n.id).join(','))

watch(
  graphKey,
  () => {
    nextTick(() => {
      ensureLayout()
      nextTick(() => {
        if (!fitAll()) requestAnimationFrame(() => fitAll())
      })
    })
  },
  { immediate: true },
)

function nodeById(id: string) {
  return nodes.value.find((n) => n.id === id)
}

function edgePath(e: GraphEdge) {
  const a = nodeById(e.from)
  const b = nodeById(e.to)
  if (!a || !b) return ''
  const x1 = (a.x || 0) + NODE_W
  const y1 = (a.y || 0) + NODE_H / 2
  const x2 = b.x || 0
  const y2 = (b.y || 0) + NODE_H / 2
  const mid = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`
}

function edgeLabelPos(e: GraphEdge) {
  const a = nodeById(e.from)
  const b = nodeById(e.to)
  if (!a || !b) return { x: 0, y: 0 }
  return {
    x: ((a.x || 0) + NODE_W + (b.x || 0)) / 2,
    y: ((a.y || 0) + (b.y || 0) + NODE_H) / 2 - 8,
  }
}

function nodeIdAt(clientX: number, clientY: number) {
  const el = viewportEl.value
  if (!el) return ''
  const r = el.getBoundingClientRect()
  const x = (clientX - r.left - panX.value) / zoom.value
  const y = (clientY - r.top - panY.value) / zoom.value
  for (let i = nodes.value.length - 1; i >= 0; i--) {
    const n = nodes.value[i]
    const nx = n.x || 0
    const ny = n.y || 0
    if (x >= nx - 8 && x <= nx + NODE_W + 8 && y >= ny - 8 && y <= ny + NODE_H + 8) return n.id
  }
  return ''
}

function onPortDown(ev: PointerEvent, n: GraphNode) {
  ev.stopPropagation()
  ev.preventDefault()
  selectedId.value = ''
  linkingFrom.value = n.id
  linkHoverId.value = ''
  const p = worldPoint(ev)
  drag.value = { kind: 'link', from: n.id, x: p.x, y: p.y }
  viewportEl.value?.setPointerCapture?.(ev.pointerId)
}

function onNodeDown(ev: PointerEvent, n: GraphNode) {
  if ((ev.target as HTMLElement).closest('.port')) return
  ev.stopPropagation()
  if (linkingFrom.value && linkingFrom.value !== n.id) {
    finishLink(n.id)
    return
  }
  linkingFrom.value = ''
  linkHoverId.value = ''
  const p = worldPoint(ev)
  drag.value = {
    kind: 'node',
    id: n.id,
    dx: p.x - (n.x || 0),
    dy: p.y - (n.y || 0),
    sx: ev.clientX,
    sy: ev.clientY,
    moved: false,
  }
  ;(ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId)
}

function onViewportDown(ev: PointerEvent) {
  if ((ev.target as HTMLElement).closest('.node, .port, .edge-label')) return
  selectedId.value = ''
  linkingFrom.value = ''
  linkHoverId.value = ''
  drag.value = { kind: 'pan', x: ev.clientX, y: ev.clientY, ox: panX.value, oy: panY.value }
  viewportEl.value?.setPointerCapture?.(ev.pointerId)
}

function onPointerMove(ev: PointerEvent) {
  if (!drag.value) return
  if (drag.value.kind === 'pan') {
    panX.value = drag.value.ox + ev.clientX - drag.value.x
    panY.value = drag.value.oy + ev.clientY - drag.value.y
    return
  }
  if (drag.value.kind === 'link') {
    const p = worldPoint(ev)
    drag.value = { ...drag.value, x: p.x, y: p.y }
    const hid = nodeIdAt(ev.clientX, ev.clientY)
    linkHoverId.value = hid && hid !== drag.value.from ? hid : ''
    return
  }
  if (
    !drag.value.moved &&
    Math.hypot(ev.clientX - drag.value.sx, ev.clientY - drag.value.sy) > 4
  ) {
    drag.value.moved = true
  }
  if (!drag.value.moved) return
  const p = worldPoint(ev)
  patchNode(drag.value.id, {
    x: Math.round(p.x - drag.value.dx),
    y: Math.round(p.y - drag.value.dy),
  })
}

function onPointerUp(ev?: PointerEvent) {
  const cur = drag.value
  drag.value = null
  if (!cur) return
  if (cur.kind === 'link') {
    const to = ev ? nodeIdAt(ev.clientX, ev.clientY) : ''
    if (to && to !== cur.from) finishLink(to)
    else linkingFrom.value = cur.from
    linkHoverId.value = ''
    return
  }
  if (cur.kind !== 'node' || cur.moved) return
  selectedId.value = cur.id
}

function onPointerLeave() {
  if (drag.value?.kind === 'pan') onPointerUp()
}

const linkPreview = computed(() => {
  const cur = drag.value
  if (!cur || cur.kind !== 'link') return ''
  const a = nodeById(cur.from)
  if (!a) return ''
  const x1 = (a.x || 0) + NODE_W
  const y1 = (a.y || 0) + NODE_H / 2
  const mid = (x1 + cur.x) / 2
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${cur.y}, ${cur.x} ${cur.y}`
})

function onWheel(ev: WheelEvent) {
  ev.preventDefault()
  const el = viewportEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12
  setZoomAt(zoom.value * factor, ev.clientX - r.left, ev.clientY - r.top)
}

function finishLink(toId: string) {
  const from = linkingFrom.value
  linkingFrom.value = ''
  linkHoverId.value = ''
  if (!from || from === toId) return
  if (edges.value.some((e) => e.from === from && e.to === toId)) return
  commit({ nodes: nodes.value, edges: [...edges.value, { from, to: toId }] })
}

function addNode(type: string) {
  const id = `${type}_${Math.random().toString(36).slice(2, 7)}`
  const maxX = nodes.value.reduce((m, n) => Math.max(m, n.x || 0), 40)
  commit({
    nodes: [
      ...nodes.value,
      { id, type, label: typeLabel(type), config: {}, x: maxX + 220, y: 36 },
    ],
    edges: edges.value,
  })
  selectedId.value = id
}

function removeNode() {
  const id = selectedId.value
  if (!id) return
  commit({
    nodes: nodes.value.filter((n) => n.id !== id),
    edges: edges.value.filter((e) => e.from !== id && e.to !== id),
  })
  selectedId.value = ''
}

function removeEdge(e: GraphEdge) {
  commit({
    nodes: nodes.value,
    edges: edges.value.filter((x) => !(x.from === e.from && x.to === e.to && (x.when || '') === (e.when || ''))),
  })
}

function setSelected(field: 'id' | 'type' | 'label', value: string) {
  const n = selected.value
  if (!n) return
  if (field === 'id') {
    const nextId = value.trim()
    if (!nextId || nextId === n.id || nodes.value.some((x) => x.id === nextId)) return
    commit({
      nodes: nodes.value.map((x) => (x.id === n.id ? { ...x, id: nextId } : x)),
      edges: edges.value.map((e) => ({
        ...e,
        from: e.from === n.id ? nextId : e.from,
        to: e.to === n.id ? nextId : e.to,
      })),
    })
    selectedId.value = nextId
    return
  }
  patchNode(n.id, { [field]: value })
}

function setConfigText(raw: string) {
  const n = selected.value
  if (!n) return
  try {
    const parsed = JSON.parse(raw || '{}')
    if (parsed && typeof parsed === 'object') patchNode(n.id, { config: parsed })
  } catch {
    /* keep typing */
  }
}

function setEdgeWhen(e: GraphEdge, when: string) {
  commit({
    nodes: nodes.value,
    edges: edges.value.map((x) =>
      x.from === e.from && x.to === e.to ? { ...x, when: when || undefined } : x,
    ),
  })
}

const selectedConfig = computed(() => JSON.stringify(selected.value?.config || {}, null, 2))
const outgoing = computed(() => edges.value.filter((e) => e.from === selectedId.value))
const worldStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
}))

const worldExtent = computed(() => {
  const box = contentBox()
  return {
    w: Math.max(960, box.minX + box.w + 280),
    h: Math.max(640, box.minY + box.h + 280),
  }
})
</script>

<template>
  <div class="canvas-wrap">
    <div class="toolbar">
      <button v-for="t in TYPES" :key="t.id" type="button" class="btn" :class="t.id" @click="addNode(t.id)">
        + {{ t.label }}
      </button>
      <span class="spacer" />
      <button type="button" class="btn" @click="zoomBy(1 / 1.15)">−</button>
      <span class="zoom">{{ zoomLabel }}</span>
      <button type="button" class="btn" @click="zoomBy(1.15)">+</button>
      <button type="button" class="btn" @click="fitAll(true)">适应</button>
      <button type="button" class="btn" @click="resetView">100%</button>
      <span v-if="linkingFrom" class="hint">拖到目标节点松手，或再点一下目标</span>
      <span v-else class="hint">从右侧圆点拖出连线 · 拖空白处平移</span>
    </div>
    <div class="board">
      <div
        ref="viewportEl"
        class="viewport"
        :class="{ grabbing: drag?.kind === 'pan', linking: !!linkingFrom }"
        @pointerdown="onViewportDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerLeave"
        @wheel.prevent="onWheel"
      >
        <div class="world" :style="worldStyle">
          <svg class="wires" :width="worldExtent.w" :height="worldExtent.h">
            <path
              v-for="(e, i) in edges"
              :key="i"
              :d="edgePath(e)"
              class="wire"
              @click.stop="selectedId = e.from"
            />
            <path v-if="linkPreview" :d="linkPreview" class="wire preview" />
          </svg>
          <button
            v-for="(e, i) in edges"
            :key="'el' + i"
            type="button"
            class="edge-label"
            :style="{ left: edgeLabelPos(e).x + 'px', top: edgeLabelPos(e).y + 'px' }"
            @click.stop="removeEdge(e)"
            :title="e.when || '点击删除连线'"
          >
            {{ e.when || '→' }}
          </button>
          <article
            v-for="n in nodes"
            :key="n.id"
            class="node"
            :data-node-id="n.id"
            :class="[n.type, { on: selectedId === n.id, link: linkingFrom === n.id, drop: linkHoverId === n.id }]"
            :style="{ left: (n.x || 0) + 'px', top: (n.y || 0) + 'px' }"
            @pointerdown="onNodeDown($event, n)"
            @click.stop
          >
            <span class="kind">{{ typeLabel(n.type) }}</span>
            <strong>{{ n.label || n.id }}</strong>
            <button type="button" class="port" title="拖出连线" @pointerdown="onPortDown($event, n)" />
          </article>
        </div>
      </div>
    </div>
    <Teleport to="body">
      <div v-if="selected" class="drawer-mask" @click.self="selectedId = ''">
        <aside class="drawer">
          <header class="drawer-head">
            <div>
              <h3>节点</h3>
              <p class="hint">{{ typeLabel(selected.type) }} · {{ selected.id }}</p>
            </div>
            <button type="button" class="btn" @click="selectedId = ''">关闭</button>
          </header>
          <form class="node-form" @submit.prevent>
             <div class="pair">
              <label>
                ID
                <input :value="selected.id" @change="setSelected('id', ($event.target as HTMLInputElement).value)" />
              </label>
              <label>
                类型
                <input :value="typeLabel(selected.type)" readonly />
              </label>
            </div>
            <label>
              名称
              <input :value="selected.label" @change="setSelected('label', ($event.target as HTMLInputElement).value)" />
            </label>
            <label>
              配置
              <textarea :value="selectedConfig" rows="8" @change="setConfigText(($event.target as HTMLTextAreaElement).value)" />
            </label>
            <div v-if="outgoing.length" class="outs">
              <h4>连出</h4>
              <div v-for="(e, i) in outgoing" :key="i" class="out">
                <span>→ {{ e.to }}</span>
                <input
                  :value="e.when || ''"
                  placeholder="条件，如 score_ok == true"
                  @change="setEdgeWhen(e, ($event.target as HTMLInputElement).value)"
                />
                <button type="button" class="btn" @click="removeEdge(e)">删线</button>
              </div>
            </div>
            <button type="button" class="btn danger" @click="removeNode">删除节点</button>
          </form>
        </aside>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.canvas-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  flex: 1;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding:12px 0px;
  align-items: center;
}
.spacer { flex: 1; min-width: 8px; }
.zoom {
  min-width: 3.2rem;
  text-align: center;
  font-size: 12px;
  color: #6b6458;
}
.hint {
  font-size: 12px;
  color: #6b6458;
}
.board {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  min-height: 0;
  flex: 1;
  height: min(68vh, 640px);
}
.viewport {
  position: relative;
  overflow: hidden;
  min-height: 420px;
  height: 100%;
  border: 1px solid #e2e6eb;
  border-radius: 6px;
  background:
    radial-gradient(circle at 1px 1px, #e7ebef 1px, transparent 0) 0 0 / 18px 18px;
  cursor: grab;
  touch-action: none;
}
.viewport.grabbing { cursor: grabbing; }
.viewport.linking { cursor: crosshair; }
.viewport.linking .wire { pointer-events: none; }
.world {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
  will-change: transform;
}
.wires {
  position: absolute;
  left: 0;
  top: 0;
  overflow: visible;
  pointer-events: none;
}
.wire {
  fill: none;
  stroke: #9aa3ad;
  stroke-width: 1.6;
  pointer-events: stroke;
  cursor: pointer;
}
.wire.preview {
  stroke: #0f6a5a;
  stroke-dasharray: 6 4;
  pointer-events: none;
}
.edge-label {
  position: absolute;
  transform: translate(-50%, -50%);
  border: 0;
  background: #fff;
  color: #6b6458;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.node {
  position: absolute;
  width: 168px;
  min-height: 62px;
  padding: 8px 14px 8px 10px;
  border: 1px solid #d7dde3;
  border-radius: 6px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: grab;
  box-shadow: 0 1px 0 rgba(28, 25, 23, 0.04);
  user-select: none;
}
.node.on {
  border-color: #0f6a5a;
  box-shadow: 0 0 0 2px rgba(15, 106, 90, 0.16);
}
.node.link { border-color: #7a5b32; }
.node.drop {
  border-color: #0f6a5a;
  box-shadow: 0 0 0 2px rgba(15, 106, 90, 0.2);
}
.node .kind { font-size: 11px; color: #6b6458; }
.node strong { font-size: 13px; font-weight: 650; }
.port {
  position: absolute;
  right: -8px;
  top: 50%;
  width: 14px;
  height: 14px;
  margin-top: -7px;
  border: 2px solid #0f6a5a;
  background: #fff;
  border-radius: 50%;
  padding: 0;
  cursor: crosshair;
  z-index: 2;
}
.port::after {
  content: '';
  position: absolute;
  inset: -10px;
}
.node.start, .btn.start { background: #f3f5f7; }
.node.approval, .btn.approval { background: #eef6f3; }
.node.condition, .btn.condition { background: #f8f3ea; }
.node.action, .btn.action { background: #eef3f8; }
.node.extract, .node.score, .btn.extract, .btn.score { background: #f3eef8; }
.node.delay, .btn.delay { background: #f6eee8; }
.node.end, .btn.end { background: #f4f1ee; }
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
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.drawer-head h3 { margin: 0 0 4px; font-size: 1.05rem; }
.drawer label {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: #6b6458;
}
.drawer input,
.drawer select,
.drawer textarea {
  width: 100%;
  border: 1px solid #d7dde3;
  border-radius: 4px;
  padding: 6px 8px;
  font: inherit;
  color: #1c1914;
  background: #fff;
}
.drawer textarea { font-family: ui-monospace, monospace; font-size: 12px; }
.drawer input[readonly] {
  background: #f6f8fa;
  color: #6b6458;
}
.node-form { display: grid; gap: 10px; }
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.outs { display: grid; gap: 8px; }
.out { display: grid; gap: 4px; font-size: 12px; }
.btn {
  padding: 5px 10px;
  border-radius: 4px;
  border: 1px solid #d7dde3;
  background: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.btn.danger { color: #a33b2b; border-color: #e8c4be; }
</style>
