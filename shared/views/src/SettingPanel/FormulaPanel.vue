<script setup lang="ts">
/**
 * 公式设置 — 某一绑定模型下的公式规则。
 * status: active(启用) / expired(过期，由时间自动从启用过渡) / disabled(停用)
 * base_cfg: mod=fleet · type=formula
 */
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import {
  dateRangeFromDraft,
  draftFromDateRange,
  fetchSchema,
  fieldKey,
  filterOps,
  isNumericField,
  needsValue,
  needsValue2,
  type SchemaField,
} from '@modoor/hooks'
import DateRange from '@modoor/widget/DateRange'
import FormulaSheet from './FormulaSheet.vue'

type Kind = 'income' | 'expense'
/** 生效 / 过期 / 停用 */
type RuleStatus = 'active' | 'expired' | 'disabled'

/** 与 query FilterDraft 对齐（另带 field） */
type MatchCond = {
  field: string
  op: string
  value: string
  value2: string
}

type FormulaRule = {
  uukey: string
  label: string
  kind: Kind
  status: RuleStatus
  model: string
  match: { all: MatchCond[] }
  apply: { target: string; formula: string; depends?: string[] }
}

type FormulaConfig = {
  version: number
  rules: FormulaRule[]
}

const STATUS_TABS: { value: RuleStatus; label: string }[] = [
  { value: 'active', label: '启用' },
  { value: 'expired', label: '过期' },
  { value: 'disabled', label: '停用' },
]

type MenuAction =
  | { kind: 'status'; status: RuleStatus; label: string }
  | { kind: 'delete'; label: string }

/**
 * ··· 菜单：
 * - 启用 tab：仅「停用」
 * - 停用 tab：仅「启用」+「删除」
 * - 过期：时间自动从启用过渡而来，可「启用」复活或「停用」归档，无删除
 */
function menuActions(status: RuleStatus): MenuAction[] {
  if (status === 'active') return [{ kind: 'status', status: 'disabled', label: '停用' }]
  if (status === 'disabled') {
    return [
      { kind: 'status', status: 'active', label: '启用' },
      { kind: 'delete', label: '删除' },
    ]
  }
  return [
    { kind: 'status', status: 'active', label: '启用' },
    { kind: 'status', status: 'disabled', label: '停用' },
  ]
}

function normalizeStatus(raw: unknown): RuleStatus {
  const s = String(raw || '').toLowerCase()
  if (s === 'active' || s === '生效' || s === '启用') return 'active'
  if (s === 'expired' || s === '过期') return 'expired'
  if (s === 'disabled' || s === '停用') return 'disabled'
  return 'active'
}

const props = withDefaults(
  defineProps<{
    /** 当前页签绑定模型，如 fleet.freight / fleet.mileage */
    model: string
    /** 公式规则保存接口 */
    endpoint?: string
    /** base_cfg 的 mod（公式规则读取） */
    configMod?: string
    /** 未保存时是否展示内置默认规则（fleet 用） */
    useDefaults?: boolean
  }>(),
  {
    endpoint: '/api/fleet/formula-settings',
    configMod: 'fleet',
    useDefaults: true,
  },
)

const TYPE = 'formula'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
/** 全量规则（含其它 model） */
const allRules = ref<FormulaRule[]>([])
const selected = ref('')
const schemaFields = ref<SchemaField[]>([])
/** 左侧状态 tab：筛选列表 */
const statusTab = ref<RuleStatus>('active')
const menuOpen = ref('')
const dictRule = ref<FormulaRule | null>(null)

function todayStamp(): string {
  const now = new Date()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${m}-${d}`
}

/** 结束日期早于今天只用于页签展示，不改存储的 status。 */
function utimeEnd(rule: FormulaRule): string {
  const cond = rule.match.all.find((c) => c.field === 'basic.utime')
  if (!cond || cond.op !== 'BTW') return ''
  return String(cond.value2 || '').trim().slice(0, 10)
}

function isDisplayExpired(rule: FormulaRule): boolean {
  const end = utimeEnd(rule)
  return !!end && end < todayStamp()
}

function shownInTab(rule: FormulaRule, tab: RuleStatus): boolean {
  if (rule.model !== props.model) return false
  if (tab === 'disabled') return rule.status === 'disabled'
  if (tab === 'expired') return rule.status === 'expired' || (rule.status === 'active' && isDisplayExpired(rule))
  return rule.status === 'active' && !isDisplayExpired(rule)
}

const modelRules = computed(() => allRules.value.filter((r) => shownInTab(r, statusTab.value)))

const active = computed(() => allRules.value.find((r) => r.uukey === selected.value) || null)

const numFields = computed(() =>
  schemaFields.value
    .filter((f) => isNumericField(f) && fieldKey(f))
    .map((f) => {
      const value = fieldKey(f)
      const label = String(f.label || value)
      return { value, label: `${label} (${value})` }
    })
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN')),
)

const matchFields = computed(() =>
  schemaFields.value
    .filter((f) => fieldKey(f) && f.field && f.field !== 'model' && f.field !== 'state')
    .map((f) => {
      const value = fieldKey(f)
      return { value, label: `${f.label || value} (${value})`, field: f }
    }),
)

function kindOfModel(model: string): Kind {
  return model === 'fleet.freight' ? 'income' : 'expense'
}

function defaultTarget(): string {
  return numFields.value[0]?.value || ''
}

function findField(key: string): SchemaField | undefined {
  return schemaFields.value.find((f) => fieldKey(f) === key)
}

function ftypeOf(f: SchemaField | undefined) {
  return String(f?.ftype || '').toUpperCase()
}

function normalizeOp(raw: string): string {
  const op = String(raw || 'EQ').toUpperCase()
  if (op === 'GTE') return 'GE'
  if (op === 'LTE') return 'LE'
  return op
}

/** match 不用 ALL；其余与 query filterOps 一致 */
function matchOpsFor(fieldKeyStr: string) {
  const f = findField(fieldKeyStr)
  const ops = f ? filterOps(f) : [{ value: 'EQ', label: '等于' }]
  return ops.filter((o) => o.value !== 'ALL')
}

function defaultOpFor(fieldKeyStr: string): string {
  return matchOpsFor(fieldKeyStr)[0]?.value || 'EQ'
}

function emptyCond(): MatchCond {
  const field = findField('basic.utime') ? 'basic.utime' : matchFields.value[0]?.value || ''
  const op = field && ftypeOf(findField(field)) === 'DATETIME' ? 'BTW' : defaultOpFor(field)
  return { field, op, value: '', value2: '' }
}

function onMatchFieldChange(c: MatchCond) {
  c.op = defaultOpFor(c.field)
  if (ftypeOf(findField(c.field)) === 'DATETIME') {
    c.op = 'BTW'
  }
  c.value = ''
  c.value2 = ''
}

function dateStart(c: MatchCond) {
  if (c.op === 'BTW') return String(c.value || '').slice(0, 10)
  return dateRangeFromDraft(c).start
}

function dateEnd(c: MatchCond) {
  if (c.op === 'BTW') return String(c.value2 || '').slice(0, 10)
  return dateRangeFromDraft(c).end
}

function onDateRangeChange(c: MatchCond, payload: { start: string; end: string }) {
  if (c.field === 'basic.utime') {
    c.op = 'BTW'
    c.value = payload.start
    c.value2 = payload.end
    return
  }
  const next = draftFromDateRange(payload.start, payload.end)
  if (!next) {
    c.op = 'BTW'
    c.value = ''
    c.value2 = ''
    return
  }
  c.op = next.op
  c.value = next.value
  c.value2 = next.value2
}

async function loadSchema() {
  try {
    const res = await fetchSchema(props.model, 'default', 'SEARCH')
    schemaFields.value = (res.table?.fields || []) as SchemaField[]
  } catch {
    schemaFields.value = []
  }
}

function emptyRule(): FormulaRule {
  const id = `rule_${Date.now().toString(36)}`
  const isMileage = props.model === 'fleet.mileage'
  const kind = kindOfModel(props.model)
  return {
    uukey: id,
    label: '新规则',
    kind,
    status: statusTab.value === 'disabled' ? 'disabled' : 'active',
    model: props.model,
    match: { all: [emptyCond()] },
    apply: {
      target: defaultTarget(),
      formula: isMileage ? 'mileage.national * 1' : '1',
      depends: [],
    },
  }
}

function seedRule(
  uukey: string,
  label: string,
  model: string,
  target: string,
  formula: string,
  period: { start?: string; end?: string } = {},
): FormulaRule {
  return {
    uukey,
    label,
    kind: kindOfModel(model),
    status: 'active',
    model,
    match: {
      all: [
        {
          field: 'basic.utime',
          op: 'BTW',
          value: period.start || '',
          value2: period.end || '',
        },
      ],
    },
    apply: { target, formula, depends: [] },
  }
}

const FREIGHT_BEFORE_20260801 =
  'IFS(goods.mileage<=30, goods.quantity*22.5, goods.mileage<=50, goods.quantity*goods.mileage*0.697, goods.mileage<=100, goods.quantity*goods.mileage*0.674, goods.mileage>100, goods.quantity*goods.mileage*IF(goods.tollFee>0, 0.641, 0.639))/1000+(goods.tollFee*goods.quantity)/1000'
const FREIGHT_FROM_20260801 =
  'IFS(basic.bizType=="BulkSupply", goods.mileage*goods.quantity*0.74, goods.mileage<=30, goods.quantity*23.34, goods.mileage<=50, goods.quantity*goods.mileage*0.723, goods.mileage<=100, goods.quantity*goods.mileage*0.699, goods.mileage>100, goods.quantity*goods.mileage*IF(goods.tollFee>0, 0.663, 0.663))/1000+(goods.tollFee*goods.quantity)/1000'
const TRIP_BEFORE_20261013 =
  'IFS(basic.tanks==2, basic.trips*60, basic.tanks==3, basic.trips*70, basic.tanks==4, basic.trips*100, true, 0)+(mileage.complete-mileage.start)*0'
const TRIP_FROM_20261013 =
  'IFS(basic.tanks==2, basic.trips*60, basic.tanks==3, basic.trips*70, basic.tanks==4, basic.trips*120, true, 0)+(mileage.complete-mileage.start)*0'

/** 一条规则对应一整段公式，只按出车日期分段。 */
function defaultConfig(): FormulaConfig {
  if (!props.useDefaults) return { version: 1, rules: [] }
  const mileage = 'fleet.mileage'
  const freight = 'fleet.freight'
  return {
    version: 1,
    rules: [
      seedRule(
        'mileage_national',
        '公路运费',
        mileage,
        'expense.nationalWage',
        'IFS(basic.tanks==2, mileage.national*0.7, basic.tanks==3, mileage.national*0.8, basic.tanks==4, mileage.national*0.8, true, 0)',
      ),
      seedRule(
        'mileage_highway',
        '高速运费',
        mileage,
        'expense.highwayWage',
        'IFS(basic.tanks==2, mileage.highway*0.6, basic.tanks==3, mileage.highway*0.65, basic.tanks==4, mileage.highway*0.7, true, 0)',
      ),
      seedRule(
        'mileage_trip_from_20261013',
        '出车费（2026-10-13起）',
        mileage,
        'expense.tripFee',
        TRIP_FROM_20261013,
        { start: '2026-10-13' },
      ),
      seedRule(
        'mileage_trip_before_20261013',
        '出车费（2026-10-12止）',
        mileage,
        'expense.tripFee',
        TRIP_BEFORE_20261013,
        { end: '2026-10-12' },
      ),
      seedRule(
        'mileage_driver',
        '司机工资',
        mileage,
        'expense.driverIncome',
        'IFS(basic.crewMode=="SINGLE", expense.quality*0.68, basic.crewMode=="DOUBLE", expense.quality*0.6, true, 0)',
      ),
      seedRule(
        'mileage_escort',
        '押运员工资',
        mileage,
        'expense.escortIncome',
        'IFS(basic.crewMode=="SINGLE", expense.quality*0.34, basic.crewMode=="DOUBLE", expense.quality*0.6, true, 0)',
      ),
      seedRule(
        'mileage_quality',
        '绩效工资',
        mileage,
        'expense.quality',
        'basic.sealings*25+expense.tripFee+expense.nationalWage+expense.highwayWage',
      ),
      seedRule(
        'freight_from_20260801',
        '收入运费（2026-08-01起）',
        freight,
        'goods.freight',
        FREIGHT_FROM_20260801,
        { start: '2026-08-01' },
      ),
      seedRule(
        'freight_before_20260801',
        '收入运费（2026-07-31止）',
        freight,
        'goods.freight',
        FREIGHT_BEFORE_20260801,
        { end: '2026-07-31' },
      ),
    ],
  }
}

function normalizeCond(c: Record<string, unknown>): MatchCond {
  const field = String(c.field || '')
  return {
    field,
    op: field === 'basic.utime' ? 'BTW' : normalizeOp(String(c.op || 'EQ')),
    value: String(c.value ?? ''),
    value2: String(c.value2 ?? ''),
  }
}

function normalize(raw: unknown): FormulaConfig {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return defaultConfig()
  const obj = raw as Record<string, unknown>
  if (Array.isArray(obj) || Array.isArray((raw as { data?: unknown }).data)) {
    return defaultConfig()
  }
  const list = Array.isArray(obj.rules) ? obj.rules : []
  const rulesNorm: FormulaRule[] = []
  for (const item of list) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const model = String(r.model || 'fleet.mileage')
    const matchRaw = (r.match && typeof r.match === 'object' ? r.match : {}) as {
      all?: unknown
    }
    const all = Array.isArray(matchRaw.all) ? matchRaw.all : []
    const applyRaw = (r.apply && typeof r.apply === 'object' ? r.apply : {}) as Record<
      string,
      unknown
    >
    rulesNorm.push({
      uukey: String(r.uukey || `rule_${rulesNorm.length + 1}`),
      label: String(r.label || r.uukey || '未命名'),
      kind: kindOfModel(model),
      status: normalizeStatus(r.status ?? (r.enabled === false ? 'disabled' : 'active')),
      model,
      match: {
        all: all
          .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
          .map(normalizeCond),
      },
      apply: {
        target: String(applyRaw.target || ''),
        formula: String(applyRaw.formula || applyRaw.expr || ''),
        depends: Array.isArray(applyRaw.depends)
          ? applyRaw.depends.map((item) => String(item || '').trim()).filter(Boolean)
          : [],
      },
    })
  }
  return { version: Number(obj.version || 1), rules: rulesNorm.length ? rulesNorm : defaultConfig().rules }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(
      `/api/base/config/item?mod=${encodeURIComponent(props.configMod)}&type=${encodeURIComponent(TYPE)}`,
      { credentials: 'include' },
    )
    if (!res.ok) throw new Error(await res.text())
    const body = await res.json()
    const item = body.item
    let cfg = defaultConfig()
    if (item?.data != null) {
      if (Array.isArray(item.data) && item.data[0]?.uukey === '_json') {
        try {
          cfg = normalize(JSON.parse(String(item.data[0].value || '{}')))
        } catch {
          cfg = defaultConfig()
        }
      } else {
        cfg = normalize(item.data)
      }
    }
    allRules.value = cfg.rules
    const first = allRules.value.find((r) => r.model === props.model)
    selected.value = first?.uukey || ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    allRules.value = defaultConfig().rules
    const first = allRules.value.find((r) => r.model === props.model)
    selected.value = first?.uukey || ''
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const others = allRules.value.filter((r) => r.model !== props.model)
    const mine = allRules.value
      .filter((r) => r.model === props.model)
      .map((r) => ({ ...r, kind: kindOfModel(props.model), model: props.model }))
    const payload: FormulaConfig = { version: 1, rules: [...others, ...mine] }
    // 走 fleet 接口：保存前校验 IFS/语法，错误信息直接展示
    const res = await fetch(props.endpoint, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: '公式设置',
        rules: payload.rules,
      }),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      const msg =
        (body as { error?: { message?: string } })?.error?.message ||
        (body as { message?: string })?.message ||
        `保存失败 (${res.status})`
      throw new Error(msg)
    }
    const saved = (body as { rules?: FormulaRule[] }).rules
    allRules.value = Array.isArray(saved) ? saved : payload.rules
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

function addRule() {
  const r = emptyRule()
  allRules.value = [...allRules.value, r]
  selected.value = r.uukey
}

function openDict(rule: FormulaRule) {
  dictRule.value = rule
}

function onDictSaved(payload: { match: string[] }) {
  const rule = dictRule.value
  if (rule) {
    rule.apply.depends = [
      ...new Set([...(rule.apply.depends || []), ...payload.match]),
    ]
  }
  dictRule.value = null
}

function selectFirstInTab() {
  const list = allRules.value.filter((r) => shownInTab(r, statusTab.value))
  if (!list.some((r) => r.uukey === selected.value)) {
    selected.value = list[0]?.uukey || ''
  }
}

function removeRule(uukey: string) {
  menuOpen.value = ''
  allRules.value = allRules.value.filter((r) => r.uukey !== uukey)
  selectFirstInTab()
}

function setRuleStatus(uukey: string, status: RuleStatus) {
  const r = allRules.value.find((x) => x.uukey === uukey)
  if (r) r.status = status
  menuOpen.value = ''
  // 改状态后可能离开当前 tab
  selectFirstInTab()
}

function toggleMenu(uukey: string) {
  menuOpen.value = menuOpen.value === uukey ? '' : uukey
}

function onDocClick() {
  menuOpen.value = ''
}

function addMatch() {
  if (!active.value) return
  active.value.match.all.push(emptyCond())
}

function removeMatch(i: number) {
  if (!active.value) return
  active.value.match.all.splice(i, 1)
}

watch(statusTab, () => {
  menuOpen.value = ''
  selectFirstInTab()
})

onMounted(async () => {
  document.addEventListener('click', onDocClick)
  await loadSchema()
  await load()
  selectFirstInTab()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
})
</script>

<template>
  <div class="computed-panel">
    <header class="ph">
      <div class="ph-left">
        <slot name="tabs" />
        <p class="muted">
          针对 <code>{{ model }}</code>：match 匹配行后按公式写回数值字段
        </p>
      </div>
      <div class="ph-actions">
        <button type="button" class="btn" @click="addRule">+ 规则</button>
        <button type="button" class="btn primary" :disabled="saving || loading" @click="save">
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="err">{{ error }}</p>
    <p v-else-if="loading" class="muted load">加载中…</p>

    <div v-else class="layout">
      <aside class="side">
        <nav class="side-tabs" aria-label="rule-status">
          <button
            v-for="s in STATUS_TABS"
            :key="s.value"
            type="button"
            class="side-tab"
            :class="{ on: statusTab === s.value }"
            @click="statusTab = s.value"
          >
            {{ s.label }}
          </button>
        </nav>
        <nav class="nav">
          <div
            v-for="r in modelRules"
            :key="r.uukey"
            class="nav-item"
            :class="{ active: r.uukey === selected }"
            @click="selected = r.uukey"
          >
            <span class="t">{{ r.label }}</span>
            <div class="more" @click.stop>
              <button
                type="button"
                class="more-btn"
                aria-label="更多"
                @click="toggleMenu(r.uukey)"
              >
                ···
              </button>
              <div v-if="menuOpen === r.uukey" class="more-menu" @click.stop>
                <template v-for="(a, ai) in menuActions(r.status)" :key="ai">
                  <button
                    v-if="a.kind === 'status'"
                    type="button"
                    class="more-item"
                    @click="setRuleStatus(r.uukey, a.status)"
                  >
                    {{ a.label }}
                  </button>
                  <button
                    v-else
                    type="button"
                    class="more-item danger"
                    @click="removeRule(r.uukey)"
                  >
                    {{ a.label }}
                  </button>
                </template>
              </div>
            </div>
          </div>
          <p v-if="!modelRules.length" class="muted empty">暂无规则</p>
        </nav>
      </aside>

      <div v-if="active && active.model === model" class="rule-body">
        <div class="row2">
          <label>
            <span>名称</span>
            <input v-model="active.label" class="inp" />
          </label>
          <label>
            <span>字段</span>
            <select v-model="active.apply.target" class="inp">
              <option value="" disabled>选择数值字段</option>
              <option v-for="f in numFields" :key="f.value" :value="f.value">{{ f.label }}</option>
              <option
                v-if="active?.apply.target && !numFields.some((f) => f.value === active?.apply.target)"
                :value="active.apply.target"
              >
                {{ active.apply.target }}（不在当前 schema）
              </option>
            </select>
          </label>
          <button
            v-if="model === 'fleet.freight'"
            type="button"
            class="btn sm dict-btn"
            @click="openDict(active)"
          >
            字典
          </button>
        </div>

        <section class="block">
          <div class="block-h">
            <h3>匹配条件</h3>
            <button type="button" class="btn sm" @click="addMatch">+ 条件</button>
          </div>
          <p class="muted tip">多条件同时满足才命中。出车日期固定为介于；结束日期早于今天时出现在「过期」页，历史数据仍按区间匹配。</p>
          <div v-for="(c, i) in active.match.all" :key="i" class="cond">
            <select
              v-model="c.field"
              class="inp"
              @change="onMatchFieldChange(c)"
            >
              <option value="" disabled>选择字段</option>
              <option v-for="f in matchFields" :key="f.value" :value="f.value">{{ f.label }}</option>
              <option
                v-if="c.field && !matchFields.some((f) => f.value === c.field)"
                :value="c.field"
              >
                {{ c.field }}（不在 schema）
              </option>
            </select>
            <select v-model="c.op" class="inp op" :disabled="c.field === 'basic.utime'">
              <option v-for="o in matchOpsFor(c.field)" :key="o.value" :value="o.value">
                {{ o.label }}
              </option>
            </select>
            <div v-if="needsValue(c.op)" class="cond-val">
              <DateRange
                v-if="ftypeOf(findField(c.field)) === 'DATETIME'"
                class="dr-boxed"
                :start="dateStart(c)"
                :end="dateEnd(c)"
                short-year
                open-label="永久"
                @change="(p) => onDateRangeChange(c, p)"
              />
              <template v-else>
                <input
                  v-model="c.value"
                  class="inp"
                  :type="
                    ['NUMERIC', 'EXPENSE', 'INTEGER'].includes(ftypeOf(findField(c.field)))
                      ? 'number'
                      : 'text'
                  "
                  :placeholder="needsValue2(c.op) ? '起始' : '值'"
                />
                <input
                  v-if="needsValue2(c.op)"
                  v-model="c.value2"
                  class="inp"
                  :type="
                    ['NUMERIC', 'EXPENSE', 'INTEGER'].includes(ftypeOf(findField(c.field)))
                      ? 'number'
                      : 'text'
                  "
                  placeholder="结束"
                />
              </template>
            </div>
            <span v-else class="cond-val muted">—</span>
            <button
              type="button"
              class="icon-del"
              title="删除条件"
              aria-label="删除条件"
              @click="removeMatch(i)"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M3.5 4.5h9M6 4.5V3.5h4v1M5.5 4.5l.5 8h4l.5-8"
                  stroke="currentColor"
                  stroke-width="1.3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
          <p v-if="!active.match.all.length" class="muted">无条件 = 匹配该模型全部行</p>
        </section>

        <section class="block formula-block">
          <h3>公式</h3>
          <textarea
            v-model="active.apply.formula"
            class="inp mono formula"
            rows="5"
            placeholder="如 mileage.national*0.7"
          />
        </section>
      </div>
      <div v-else class="rule-body muted empty-body">选择或新建一条规则</div>
    </div>
  </div>

  <FormulaSheet
    v-if="dictRule"
    :rule="dictRule.uukey"
    :rule-label="dictRule.label"
    :formula="dictRule.apply.formula"
    @close="dictRule = null"
    @saved="onDictSaved"
  />
</template>

<style scoped>
.computed-panel {
  padding: 10px 16px 12px;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ph {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
  flex-shrink: 0;
}
.ph-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}
.ph-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.muted {
  margin: 0;
  font-size: 12px;
  color: var(--muted, #6b6458);
  line-height: 1.4;
}
.tip {
  margin: 0 0 8px;
}
.load {
  padding: 8px 0;
}
.err {
  color: #b42318;
  margin: 0 0 8px;
  font-size: 12px;
}
code {
  font-size: 11px;
}
.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.side {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow: hidden;
}
.side-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
  padding: 0 2px;
}
.side-tab {
  flex: 1;
  appearance: none;
  border: 0;
  background: transparent;
  padding: 5px 2px 6px;
  margin-bottom: -1px;
  font: inherit;
  font-size: 12px;
  color: var(--muted, #6b6458);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.side-tab.on {
  color: var(--ink, #1c1914);
  font-weight: 600;
  border-bottom-color: var(--ink, #1c1914);
}
.nav {
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-height: 0;
  padding: 2px 0;
}
.nav-item {
  appearance: none;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 6px 4px 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 2px;
  font: inherit;
  width: 100%;
  position: relative;
}
.nav-item .t {
  font-weight: 600;
  font-size: 13px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.more {
  position: relative;
  flex-shrink: 0;
}
.more-btn {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--muted, #6b6458);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  line-height: 1;
  letter-spacing: 0.5px;
  padding: 2px 4px;
  border-radius: 4px;
}
.more-btn:hover {
  background: #eceae4;
  color: var(--ink, #1c1914);
}
.more-menu {
  position: absolute;
  right: 0;
  top: 100%;
  z-index: 20;
  min-width: 88px;
  padding: 4px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(28, 25, 20, 0.12);
  display: flex;
  flex-direction: column;
}
.more-item {
  appearance: none;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 6px 10px;
  border-radius: 6px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  color: var(--ink, #1c1914);
}
.more-item:hover {
  background: #f3f1ec;
}
.more-item.danger {
  color: #b42318;
}
.nav-item.active {
  background: #f3f1ec;
}
.empty {
  padding: 10px 8px;
  font-size: 12px;
}
.rule-body {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 8px;
  background: #fff;
  padding: 12px 14px;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.empty-body {
  align-items: center;
  justify-content: center;
}
.row2 {
  display: grid;
  gap: 10px;
  margin-bottom: 4px;
  grid-template-columns: 1fr 1.4fr auto;
  align-items: end;
  flex-shrink: 0;
}
.dict-btn {
  height: 30px!important;
  /* margin-bottom: 1px; */
}
label span {
  display: block;
  font-size: 11px;
  color: var(--muted, #6b6458);
  margin-bottom: 3px;
}
.inp {
  width: 100%;
  box-sizing: border-box;
  padding: 5px 8px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  line-height: 1.3;
  background: #fff;
}
input.inp,
select.inp {
  height: 30px;
  padding-top: 0;
  padding-bottom: 0;
  line-height: 28px;
}
.inp.mono,
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.inp.op {
  min-width: 88px;
  width: 88px;
}
.block {
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--line, #e2e6eb);
  flex-shrink: 0;
}
.formula-block {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.block h3 {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
}
.block-h {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}
.block-h h3 {
  margin: 0;
}
.cond {
  display: grid;
  grid-template-columns: minmax(140px, 1.1fr) 88px minmax(180px, 2fr) 28px;
  gap: 6px;
  margin-bottom: 6px;
  align-items: center;
}
.cond-val {
  display: flex;
  gap: 6px;
  min-width: 0;
  align-items: center;
}
.cond-val :deep(.date-range.dr-boxed),
.cond-val :deep(.dr-boxed) {
  flex: 1;
  min-width: 0;
}
.cond-val :deep(.dr-trigger) {
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  background: #fff;
}
.cond-val :deep(.dr-trigger:hover) {
  border-color: color-mix(in srgb, var(--ink, #1c1914) 28%, var(--line, #e2e6eb));
}
.icon-del {
  appearance: none;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: 6px;
  background: #fff;
  color: #b42318;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}
.icon-del:hover {
  background: #fef3f2;
  border-color: #fecdca;
}
.formula {
  flex: 1;
  min-height: 120px;
  resize: vertical;
  line-height: 1.45;
  padding: 8px 10px;
}
.btn {
  appearance: none;
  border: 1px solid var(--line, #e2e6eb);
  background: #fff;
  padding: 4px 10px;
  height: 28px;
  border-radius: 6px;
  font: inherit;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn.sm {
  padding: 2px 8px;
  height: 24px;
  font-size: 12px;
}
.btn.primary {
  background: var(--ink, #1c1914);
  color: #fff;
  border-color: var(--ink, #1c1914);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
@media (max-width: 960px) {
  .layout {
    grid-template-columns: 1fr;
  }
  .row2,
  .cond {
    grid-template-columns: 1fr;
  }
  .icon-del {
    width: 100%;
  }
}
</style>
