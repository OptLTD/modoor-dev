# 业务模块规范（以 Fleet 为样板）

> 依据 `addon/fleet` 的落地形态整理，供后续业务模块对齐。  
> 平台级契约见 [`docs/MODULE_CONTRACT.md`](../docs/MODULE_CONTRACT.md)、[`docs/SCHEMA_CONTRACT.md`](../docs/SCHEMA_CONTRACT.md)。  
> **本文侧重：菜单 → 页面 → Tabs → Schema 列表工作台 → Action / Dialog → Query / Filter → Result / Total。**  
> 列表行内「编辑」与 SERIALNO / RELATION 点击由 **业务视图**（`SchemaView` 或自绑页面）打开 `RecordDialog` / `RecordDrawer`；`SchemaTable` 只负责表与事件。独立详情页路由仍未实现。

---

## 0. 术语与分层

| 术语 | 含义 |
|---|---|
| **Module** | 业务包（如 `fleet`），含 manifest、domain、models、webui、tools/skills |
| **Entity** | 业务模型（如 `fleet.vehicle`），对外 uukey = `<module>.<entity>` |
| **Menu** | 壳导航项，指向一个 Page |
| **Page** | 前端路由页，默认挂载 `SchemaView` |
| **Tab** | 同一 Page 内切换的 Entity 视图（一页可多模型） |
| **Schema** | `config` / `tables` / `inputs` 解释层，不替代 ORM |
| **Action / Click** | 工具栏或行级动作（`record.*` 或领域 `fleet.*`） |
| **Dialog** | 模态表单（`RecordDialog`），不是独立路由 |
| **Query** | 列表请求的固定/默认条件（`tables.query` + 运行时筛选合并） |
| **Filter** | 快捷筛选 / 侧栏 / 列头筛选，写入 appliedFilters |
| **Result** | search 返回信封：`values` / `count` / `refers` / `totals` |
| **Total** | 列表合计行数据（`totals`） |

```text
module.yaml (menu / ui-web / ability)
        │
        ▼
  webui routes  ── Page ── SchemaView（绑定 RecordDialog / RecordDrawer）
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
                  Tab(s)   SchemaTable  Sheet / Dialog
                    │         │ emits: create-request / open-record / toolbar-click
                    ▼         ▼
              models/*/   engine record API
              config|tables|inputs
                    │
                    ▼
              domain.py + adapters.py
```

**双层原则（必须遵守）：**

1. **domain**：落库真相（表、约束、tenant、领域副作用）。  
2. **models/\***：UI + 语义解释；给人 / AI / webui 用。  
3. 改字段时 **domain 与 config 双写对齐**。  
4. UI CRUD 走引擎 Record API；Agent 写库走 `exports.tools`（勿混用鉴权模型）。

---

## 1. 模块规范（Module）

### 1.1 目录

```text
addon/<module_id>/   或  builtin/<module_id>/
  module.yaml              # 必填：清单
  domain.py                # 必填：ORM + 领域规则
  adapters.py              # 必填（有 schema 实体时）：ModelAdapter 实现
  models/
    index.json             # 模型注册
    <entity>/
      config.json          # 语义：model / groups / fields / clicks
      tables.json          # 列表视图
      inputs.json          # 表单视图（可多 using）
  tools/                   # MCP tools（可窄于实体全集）
  skills/                  # Skill 文档
  webui.py                 # resolve_entry + register
  webui/                   # Vue 前端（routes + ModuleShell）
  route.py                 # 可选：模块自有 HTTP（fleet 现为空壳）
  migrations/              # 建议有；表结构演进
```

### 1.2 `module.yaml` 必备块

| 块 | 要求 |
|---|---|
| `id` / `version` / `summary` | 模块身份 |
| `ui-web` | `kind: app`，`base`，`entry`，`seqno`，`label` |
| `exports.menus` | 导航项（见 §7） |
| `exports.tools` / `exports.skills` | AI 面能力（可少于 UI 实体） |
| `ability` | 建议每实体 `*.read` / `*.write` |
| `i18n` | 至少 `zh-CN` / `en-US`：app、menus、abilities |

**Fleet 样例（节选）：**

```yaml
id: fleet
ui-web:
  kind: app
  base: /fleet
  entry: /fleet/vehicles
exports:
  menus:
    - id: fleet.vehicles
      label: Vehicles
      path: /fleet/vehicles
      seqno: 10
ability:
  - fleet.vehicle.read
  - fleet.vehicle.write
```

### 1.3 入口

- `webui.py` 必须提供 `resolve_entry(ctx) -> WebEntry`（dev URL / static dist）。  
- `register` 中应确保 adapters 注册（如 `import addon.fleet.adapters`）。  
- 前端 `base` 与壳挂载前缀一致（fleet：`/mod/fleet/`）。

### 1.4 表命名

- 模块内表前缀统一（fleet：`vms_`）。  
- 技术主键：`id`（UUID string）。  
- 业务编号：`uukey`（SERIALNO，见 §2.3）；**列表展示与 API 身份键用业务编号，不以 UUID 冒充编号。**

---

## 2. Entity 规范

### 2.1 注册

`models/index.json`：

```json
{
  "fleet.vehicle": { "path": "vehicle", "level": "business" }
}
```

- 键 = 对外模型 uukey：`<module>.<entity>`。  
- `path` = `models/` 下目录名。  
- `level`：当前统一 `business`。

### 2.2 `config.json` 四块

每个实体必须包含：`model`、`groups`、`fields`、`clicks`。

#### model

| 字段 | 说明 |
|---|---|
| `uukey` | 同 index 键 |
| `title` / `brief` | 人读标题 |
| `source` / `search` | 物理表名（可同） |
| `extra` | 可选；流水号也可写在字段 `extra` |

#### groups

| 字段 | 说明 |
|---|---|
| `uukey` | 分组短名，如 `basic` |
| `title` | 分组标题 |
| `gtype` | `FLATTEN` 或 `GROUPED`。重复多条用 `extra.multiple` |
| `seqno` | 排序 |

字段键一律：`{group}.{field}`（如 `basic.plate`）。

#### fields（核心）

| 属性 | 说明 |
|---|---|
| `field` | 短字段名 |
| `ftype` | 见 §2.4 |
| `group` / `index` / `label` / `seqno` | 分组、索引键、文案、序 |
| `extra` | `required` / `editable` / `implicit` / `multiple` / `computed` / `options` / `relation` / `constant` / `counting` / `dataType` 等 |

**每个业务实体建议靠前显式定义：**

| seqno | 键 | ftype | 说明 |
|---|---|---|---|
| 1 | `basic.uukey` | `SERIALNO` | 业务编号 |
| 2 | `basic.utime` | `DATETIME` | 业务主时间，label 跟模型走，可修改。系统创建时间 `basic.created_at` 由引擎写入，不写进 config |
| 3 | `basic.status` | `OPTIONAL` | 有状态机时必填 |

#### clicks

声明**全部可引用动作**（语义字典）。列表实际露出由 `tables.json` 的 `clicks` 数组引用子集。

| 字段 | 含义 |
|---|---|
| `ctype` | **`button`**：工具栏；**`action`**：行内 `row-actions` |
| `action` | 语义动作（`record.create` / 领域动作等） |
| `group` | 工具栏分组（如 `more`） |

| 常见 action | 默认 ctype | 含义 |
|---|---|---|
| `record.create` | button | 新建（Workspace → RecordDialog） |
| `record.delete` | button | 删除选中行 |
| `record.export` | button | 导出 |
| `record.modify` | action | 行内编辑 |
| `<module>.<domain>.…` | button / action | 领域动作，由 Workspace/Page 处理 |

`SchemaTable` **不**解释 create/delete/export；只按 `ctype` 摆位置并发出：

- `button-click` — 工具栏
- `action-click` — 行内
- `record-click` — SERIALNO / RELATION 单元格

### 2.3 SERIALNO（业务编号）

```json
"basic.uukey": {
  "field": "uukey",
  "ftype": "SERIALNO",
  "extra": {
    "required": true,
    "implicit": true,
    "editable": "INSERT",
    "constant": "VH",
    "counting": 5
  }
}
```

- 生成规则：`constant` + 零填充数字（如 `VEH00001`）。  
- 前缀 2–4 位大写，**模块内唯一**。  
- 服务端 upsert 时空号自动分配；前端 create 表单可隐藏/只读。  
- **禁止**把 UUID `id` 当作 `basic.uukey` 返回给列表。

Fleet 前缀对照：

| Entity | constant |
|---|---|
| vehicle | VH |
| maintain | MT |
| insurance | IS |
| tiremain | TR |
| tirelog | TL |
| product | PRD |
| oplog | PLG |

### 2.4 `ftype` 约定

| ftype | 用途 | UI 行为要点 |
|---|---|---|
| `SERIALNO` | 业务编号 | 新建自动编号 |
| `SUBJECT` | 主文案（车牌、名称码） | 文本 / 列表强调 |
| `STRINGS` | 普通字符串 | 文本；`dataType: LONGTEXT` → 多行 |
| `NUMERIC` / `INTEGER` / `EXPENSE` | 数值 | number；可合计 |
| `DATETIME` | 日期时间 | DateRange / date；`ONLYDATE` 仅日期 |
| `OPTIONAL` | 枚举 | Select；`options` 或 `dictKey`；可派生（见下） |
| `RELATION` | 关联 | Select（可多选 IN）；`relation` + `dataKey` + `textKey` |

通用 `extra`：

| 键 | 取值 / 说明 |
|---|---|
| `editable` | `ALWAYS` \| `INSERT` \| `NEVER` |
| `implicit` | 系统字段；表单默认隐藏（`formVisibleFields` 过滤） |
| `multiple` | 多值（多选 / 标签展示）；`OPTIONAL` / `RELATION` / `UPLOADS` 等可用 |
| `required` | 必填 |

#### `OPTIONAL` + `extra.computed`

**仅允许与 `OPTIONAL` 组合。** 表示「落库的派生枚举」：值形态仍是枚举（可多选），由 domain 写入，表单不露、不可编。

声明示例：

```json
"basic.flags": {
  "field": "flags",
  "ftype": "OPTIONAL",
  "group": "basic",
  "index": "basic.flags",
  "label": "标记",
  "seqno": 8,
  "extra": {
    "computed": true,
    "multiple": true,
    "options": [
      { "uukey": "preferred", "label": "优选" },
      { "uukey": "risk", "label": "风险" }
    ]
  }
}
```

语义（实现可归一化展开，schema 不必再写一遍）：

| 效果 | 说明 |
|---|---|
| `editable → NEVER` | 客户端 / 表单不可写 |
| `implicit → true` | 不出现在新建 / 编辑表单 |
| 仍落库 | 非虚字段；列表、详情、筛选按 `OPTIONAL` 解析 `options` |
| 写入方 | domain / adapter（事件副作用、聚合回写等） |

用法约定：

- **单值派生**：`OPTIONAL` + `computed: true` + `options`。  
- **多选 / 标签派生**：再加 `multiple: true`（`computed` 不隐含多值）。  
- **勿用于** `utime`、流水号等非枚举系统字段——那些继续用 `DATETIME` / `SERIALNO` + `editable` / `implicit`。  
- **勿用于** `RELATION` / `STRINGS` 等其它 ftype；需要派生关联或文案时另议，不复用本键。  
- 详情 / 列表要展示：照常列入 `tables` / drawer；`computed` 只管「表单隐藏 + 不可编」，不管展示。

### 2.5 Domain 不变量（样板）

写入 Spec 时每个实体应写清：

- 必填字段与默认值（如车辆 `status=idle`）。  
- 禁止操作（如 log 禁止 delete / 禁止 update）。  
- 副作用（如出入库改库存、安装改轮胎状态）。  
- FK：存技术 `id` 或业务键的策略（须在 adapter 中可解析）。

---

## 3. Tabs 规范

Tabs 是 **Page 内一等公民**，不是菜单。

### 3.1 声明位置

前端路由 `props.tabs`：

```ts
tabs: [
  { model: 'fleet.tiremain', label: '轮胎管理' },
  { model: 'fleet.tirelog', label: '安装记录' },
]
```

| 字段 | 说明 |
|---|---|
| `model` | 实体 uukey |
| `label` | Tab 文案 |
| `using` | 可选；默认列表视图 `default` |

### 3.2 行为

| 规则 | 说明 |
|---|---|
| 单 Tab | 不渲染 Tab 条，等同「当前页唯一实体」 |
| 多 Tab | 标题旁切换；切换即换 `model`，重新 `fetchSchema` + 列表 |
| 主从关系 | 主表带领域 Action；从表（log）可只读列表（`clicks: []`） |
| Sheet | 批量子表可禁用部分模型（如 append-only log） |

### 3.3 Fleet 拓扑

| Page | Tabs |
|---|---|
| 车辆 / 维保 / 保险 | 单 Tab |
| 轮胎 | `tiremain` + `tirelog` |
| 物料 | `product` + `oplog` |

---

## 4. Action 规范

### 4.1 声明与引用

1. **config.clicks**：全量字典（含 `uukey` / `label` / `action` / `seqno` / `group`）。  
2. **tables.clicks**：本列表露出的 click id 列表，如 `["create","inbound","outbound","delete"]`。

```json
"clicks": {
  "create": { "uukey": "create", "action": "record.create", "label": "新建", "seqno": 10 },
  "inbound": { "uukey": "inbound", "action": "fleet.product.inbound", "label": "入库", "seqno": 20 },
  "delete": { "uukey": "delete", "action": "record.delete", "label": "删除", "seqno": 90, "group": "more" }
}
```

### 4.2 内置 vs 领域

| 类型 | action | 默认处理方 |
|---|---|---|
| 内置 | `record.create` | Workspace 听 `button-click` → RecordDialog / handlers |
| 内置 | `record.modify` | Workspace 听 `action-click` → RecordDialog / handlers |
| 内置 | `record.open` | Workspace 听 `record-click` → Drawer / handlers |
| 内置 | `record.delete` | Workspace 听 `button-click` → delete API |
| 内置 | `record.export` | Workspace 听 `button-click` → export |
| 领域 | `fleet.tire.install` 等 | Workspace 听 `button-click` / `action-click` |

### 4.3 领域 Action 约定

- 命名：`<module>.<domain>.<verb>`。  
- 通常需要：**选中行约束**（如必须且仅 1 行）+ **打开 Dialog（指定 model + using + defaults）**。  
- 成功后刷新主表（及必要时提示切换 Tab）。  
- 工具栏「更多」：`group: "more"`；单项不强制折叠。

### 4.4 行级

- 当前标准：`SchemaTable` 只 emit；`SchemaView`（或自绑 Page）打开 RecordDialog（edit）/ RecordDrawer（detail，§13）。模块可用 `handlers` 改走全页路由。
- 行级自定义 Action：预留；现以工具栏领域动作为主。

---

## 5. Query 规范

> **相对日期（RCT / FTR）以 option-library `search` 为原始出处**（`search/consts/logic.go`、`search/schema/query.go`）。  
> 本文算子缩写与 token 命名与之对齐；引擎实现须按同名 token 展开为 `BTW`。

### 5.1 静态默认（tables.query）

```json
"query": {
  "basic.utime:RCT": "RECENT_3_MONTH"
}
```

- 键：`field`（EQ）或 `field:OP`。  
- 引擎 `parse_query` 解析；前端可将 RCT/FTR 种子化为 DateRange 草稿后与用户筛选合并。

### 5.2 算子（option-library `consts`）

| OP | 常量名 | 含义 | 值 |
|---|---|---|---|
| `EQ` | LOGIC_EQUALSTO | 等于 | 标量 |
| `NE` | LOGIC_NOTEQUAL | 不等于 | 标量 |
| `IN` | LOGIC_INCLUDES | 包含任一 | 数组 |
| `LIKE` | LOGIC_STR_LIKE | 模糊 | 字符串 |
| `HAS` | LOGIC_CONTAINS | 包含（字符串） | 标量 |
| `LT` / `LE` | LOGIC_LESTHAN / LESS_EQ | 小于 / 小于等于 | 标量 |
| `GT` / `GE` | LOGIC_GREATER / GRAT_EQ | 大于 / 大于等于 | 标量 |
| `BTW` | LOGIC_BETWEEN | 介于 | `[start, end]` |
| `RCT` | LOGIC_RECENT | 最近相对区间 | 见 §5.3 token |
| `FTR` | LOGIC_FUTURE | 未来相对区间 | 见 §5.3 token |
| `NIL` / `NNL` | VAL_NULL / NOT_NULL | 为空 / 不为空 | — |

> 说明：option-library 使用 `GE` / `LE`，**不是** `GTE` / `LTE`。Modoor 若内部 SQL 用 `GTE`/`LTE`，须在解析层把 `GE`/`LE` 视为别名，对外 query 键仍写 `GE`/`LE`。

`RCT` / `FTR` 在解析期**改写**为 `field:BTW` + `[start, end]`（与 option-library 一致），下游只认 BTW。

### 5.3 RCT / FTR Token（出处：`search/schema/query.go`）

写法：`"<field>:RCT": "<TOKEN>"` 或 `"<field>:FTR": "<TOKEN>"`。

#### 日历块（RCT / FTR 共用 switch）

| Token | 含义 |
|---|---|
| `CURRENT_WEEK` | 本周（周一～周日） |
| `PREVIOUS_WEEK` | 上周 |
| `CURRENT_MONTH` | 本月 |
| `PREVIOUS_MONTH` | 上月 |
| `CURRENT_YEAR` | 今年 |
| `PREVIOUS_YEAR` | 去年 |
| `CURRENT_TERM` / `PREVIOUS_TERM` | 本期 / 上期（依赖 term 字段；无 term 体系的模块可暂不支持） |

#### 最近（`RCT`，相对「今天」往回）

| Token | 含义 |
|---|---|
| `RECENT_3_DAYS` | 近 3 天 |
| `RECENT_1_WEEK` | 近 1 周 |
| `RECENT_2_WEEK` | 近 2 周 |
| `RECENT_1_MONTH` | 近 1 个月 |
| `RECENT_2_MONTH` | 近 2 个月 |
| `RECENT_3_MONTH` | 近 3 个月 |
| `RECENT_6_MONTH` | 近 6 个月 |

#### 未来（`FTR`，相对「今天」往前）

| Token | 含义 |
|---|---|
| `FUTURE_1_WEEK` | 未来 1 周 |
| `FUTURE_2_WEEK` | 未来 2 周 |
| `FUTURE_1_MONTH` | 未来 1 个月 |
| `FUTURE_2_MONTH` | 未来 2 个月 |
| `FUTURE_3_MONTH` | 未来 3 个月 |
| `FUTURE_6_MONTH` | 未来 6 个月 |

**语义要点（与源码一致）：**

- 锚点为「今天」本地日界；`RECENT_*_MONTH` 用 `AddDate(0, -N, 0)`（按月回退），**不是** `N_MONTHS` / 滚动 90 天，也**不是**「含当月共 N 个自然月」的另一种算法。  
- 展开结果写入 `field:BTW`，值为起止时间（源码为 RFC3339；Modoor 列表日粒度可用 `YYYY-MM-DD`，但 **token 名必须与上表一致**）。  
- **禁止**再发明 `3_MONTHS`、`3_MONTH` 等缩写作为规范写法；配置与文档一律用 `RECENT_3_MONTH`。

UI 可将 RCT/FTR 展开为 BTW 草稿以便 DateRange 展示；清空后是否恢复默认 query 由产品决定（Fleet 当前：种子一次，可清）。

### 5.4 合并规则

```text
finalQuery = merge(fixedBaseQuery, buildListQuery(appliedFilters))
```

- `tables.query` 中非 RCT/FTR 项进入固定 `baseQuery`。  
- RCT/FTR 种子进用户可改的 `appliedFilters`（展开为 BTW）。  
- **同 key 时用户筛选优先于固定 query。**

---

## 6. Filter 规范

### 6.1 声明（tables.filters）

```json
"filters": ["basic.utime", "basic.vehicle"]
```

值为字段键列表 → 工具栏**快捷筛选**。未列入的字段仍可在侧栏 FilterPanel / 列头筛选。

### 6.2 快捷筛选控件映射

| 字段 ftype | 控件 | 默认 OP |
|---|---|---|
| `OPTIONAL` | SelectBox | `EQ` |
| `RELATION` | 可搜索多选 SelectBox | `IN` |
| `DATETIME` | DateRange（预设 + 起止） | `BTW` / 单端 `GE`·`LE` |
| `STRINGS` / `SUBJECT` / … | 文本 | `LIKE` |

### 6.3 其它入口

| 入口 | 说明 |
|---|---|
| 列头 popover | 单字段草稿 → 应用 |
| 侧栏 FilterPanel | 全可筛字段；DateRange 与快捷筛选行为一致；改后自动应用 |
| 清空 | 清 appliedFilters；固定 baseQuery 仍生效 |

### 6.4 样式

快捷筛选与侧栏 DateRange：描边字段 + 浮动 label（与表单密度一致）。

---

## 7. Menu 规范

### 7.1 声明

```yaml
exports:
  menus:
    - id: fleet.reports
      label: Reports
      path: /fleet/reports
      seqno: 20
    - id: fleet.ops                 # 分组：无 path，仅 items
      label: Fleet operations
      seqno: 30
      items:
        - id: fleet.maintain
          label: Maintain
          path: /fleet/maintain
          seqno: 10
```

| 字段 | 说明 |
|---|---|
| `id` | 全局唯一，建议 `<module>.<page>`；分组同 |
| `label` | 默认文案；i18n 键同 id |
| `path` / `route` | 叶子菜单必填；分组可省略 |
| `items` | 可选嵌套菜单（壳渲染为下拉组） |
| `seqno` | 同级排序 |

### 7.2 映射

```text
Menu（叶子） ──► Vue Route ──► SchemaView / 自定义页
Menu（分组） ──► 仅导航下拉，不单独占路由
```

- 一叶子 Menu 对应一 Page。  
- 多实体用 **Tabs**，不要为每个从表单独占一级菜单（除非独立工作流）。  
- 旧路径可用 redirect 收敛到标准 Page。

### 7.3 扩展模块（挂到 host 顶栏）

独立 addon 可声明为 **extension**，菜单合并进 host 应用（不进模块切换器）：

```yaml
# addon/<host>.feature/module.yaml  （示例）
id: fleet.telematics
depends: [fleet]
ui-web:
  kind: extension
  host: fleet
  # parent: fleet.ops   # 可选：挂到 host 已有分组下
exports:
  menus:
    - id: fleet.telematics.devices
      path: /fleet/telematics
      seqno: 25
```

| 约定 | 说明 |
|---|---|
| 目录名 | 可用 `.`（如 `addon/fleet.telematics/`），与 `id` 对齐；发现按文件夹名 |
| Python 包 | 带 `.` 的目录**不能**用 `import addon.fleet.telematics`（会被当成嵌套包）；无 domain/tools 的菜单扩展可只放 `module.yaml` |
| `kind: extension` | 不进工作台切换器 |
| `host` | 目标 app 模块 id |
| `parent` | 可选，合并进 host 某分组的 `items` |
| 路由 | **页面挂在 host SPA**（如 `/mod/fleet/telematics`）；扩展目录可有 redirect-only `webui` 供 `make dev` |
| 开发 | `make dev <host>` 即可点开扩展菜单 |

本仓库当前「安全检查」已内置在 `fleet` 模块（`fleet.ops` 分组），不再单独拆 extension。

---

## 8. Page 规范

### 8.1 标准页

```ts
{
  path: 'maintain',
  name: 'fleet.maintain',
  component: SchemaView,
  props: {
    title: '维修保养',
    tabs: [{ model: 'fleet.maintain', label: '维修保养' }],
  },
}
```

| 职责 | 实现 |
|---|---|
| 标题 | `title` |
| 多视图 | `tabs` |
| 列表 | 内嵌 `SchemaTable` |
| 批量 | 可选进入 `SchemaSheet`（edit / import） |
| 领域 Dialog | 监听 `toolbar-click` |

### 8.2 壳

- `ModuleShell`：仅承载 `<RouterView />`（或模块级布局）。  
- 鉴权：webui `main` 调 `/api/auth/profile`。  
- **不要**在 Page 内重复造筛选/分页轮子；复用 `@modoor/widget`。

### 8.3 非标准页

自定义大屏、向导等可自建 Vue 页，但仍应：

- 读写走同一 Record / Tool 契约；  
- 菜单与 ability 注册完整。

---

## 9. Dialog 规范

### 9.1 载体

统一使用 **`RecordDialog`**（模态），由 `fetchInputSchema(model, using, scene, uukey?)` 驱动字段。

| 场景 | mode | using | 说明 |
|---|---|---|---|
| 工具栏新建 | create | `default`（或列表 using） | `record.create` |
| 行内编辑 | edit | 同上 | 带 uukey 拉 DETAIL |
| 领域动作 | create | 命名 using（如 `install`） | defaults 预填关联键 |

### 9.2 inputs.json

```json
{
  "default": {
    "uukey": "default",
    "fields": ["basic.plate", "basic.status", "..."],
    "preset": { "basic.status": "idle" }
  },
  "install": {
    "uukey": "install",
    "fields": ["basic.tire_id", "basic.vehicle", "basic.position"]
  }
}
```

| 规则 | 说明 |
|---|---|
| 多 using | 同一实体多套表单边界 |
| preset | 新建默认值 |
| 可编辑边界 | 跟字段 `extra.editable` |
| 提交 | `upsertRecords`；create 可合并 presets / 行 defaults |

### 9.3 交互

- 校验失败就地提示；成功关闭并 `reload` 列表。  
- 领域 Dialog 与列表 Dialog 共用组件，避免平行实现。  
- **路由级 Dialog / 抽屉详情：见 §13（RecordDrawer 已实现；独立详情页仍预留）。**

---

## 10. Schema 规范（tables / 投影）

### 10.1 tables.json

每个实体至少一个视图（建议同时提供 `default` 与 `table`，内容可相同）：

```json
{
  "default": {
    "uukey": "default",
    "title": "维修保养",
    "fields": ["basic.uukey", "basic.utime", "..."],
    "sticky": ["basic.uukey"],
    "clicks": ["create", "delete"],
    "filters": ["basic.utime", "basic.vehicle"],
    "query": { "basic.utime:RCT": "RECENT_3_MONTH" },
    "extra": {}
  }
}
```

| 字段 | 说明 |
|---|---|
| `fields` | 列顺序（字段键） |
| `sticky` | 左侧固定列 |
| `clicks` | 工具栏动作 id |
| `filters` | 快捷筛选字段 |
| `query` | 默认查询 |
| `extra` | 扩展（预留） |

### 10.2 引擎投影

`project_table` / `project_input` 输出给前端的 `SchemaTable`：

- `model` / `using` / `title` / `fields` / `clicks` / `filters` / `refers`  
- `request.query` / `request.order` / page / size  

前端 **只消费投影结果**，不直接读磁盘 JSON。

### 10.3 refers

- Adapter `refers()` 提供 RELATION / OPTIONAL 选项。  
- search 响应可合并 refers，供下拉与快捷筛选。

---

## 11. Result 规范

### 11.1 Search 信封

```json
{
  "page": 1,
  "size": 50,
  "count": 120,
  "values": [
    { "basic.uukey": "VEH00001", "basic.plate": "测A00001", "...": "..." }
  ],
  "refers": {
    "fleet.vehicle": [
      { "basic.uukey": "VEH00001", "basic.plate": "测A00001", "basic.name": "测A00001" }
    ]
  },
  "totals": null
}
```

| 字段 | 要求 |
|---|---|
| `values` | 行对象；键为 schema 字段键 |
| `count` | 总行数（分页） |
| `refers` | 可选；lookup 字典 |
| `totals` | 可选；见 §12 合计；无则 `null` |
| `basic.uukey` | **必须是业务编号** |

### 11.2 Upsert 记录信封

```json
{
  "uukey": "VEH00001",
  "model": "fleet.vehicle",
  "opType": "INSERT",
  "exists": false,
  "request": {},
  "current": {},
  "prepare": {},
  "storage": { "basic": {} },
  "changed": true,
  "changes": {},
  "objects": null
}
```

- 返回的 `uukey` = 业务编号（与 `current.basic.uukey` 一致）。  
- 批量 upsert 返回 records 数组。

### 11.3 错误

- 校验：`validation_error` + 可读 message。  
- 权限：ability / forbidden。  
- 领域冲突（库存不足等）：同样走 AppError，前端 toast。

---

## 12. Total（合计）规范

### 12.1 约定

- search 第三通道 / 响应字段 `totals`：`Record<fieldKey, number|string>`。  
- UI：当 `totals` 有键时，SchemaTable 绘制合计行；数值列右对齐格式化。  
- 典型：`basic.uukey` → 本页条数；金额字段 → 求和。

### 12.2 现状（Fleet）

- Adapter `search` 对 `NUM_KEYS` 中且出现在列表投影的字段返回 `totals`（全结果集 `sum`；`basic.uukey` → 条数）。  
- SchemaTable / TableDrawer 在有 `totals` 时绘制底部合计行。

### 12.3 实现要求（规划）

| 项 | 要求 |
|---|---|
| 范围 | 与当前 query 条件一致（全结果集，非仅当前页），或产品明确「本页合计」 |
| 字段 | 仅 NUMERIC / EXPENSE 等可加总字段；在 tables.extra 或 config 中可声明 |
| 性能 | 大表用 SQL `sum`/`count`，避免拉全量再聚 |

---

## 13. 详情展示（RecordDrawer）

列表 **SERIALNO** / **RELATION** 点击由 `SchemaTable` 发出 `open-record`；**默认在 `SchemaView` 打开 RecordDrawer**（也可在自绑 Page 上绑定）。

**RecordDrawer 只做壳**（遮罩 / 顶栏关闭 / 中间 slot / 可选 footer）。内容由模块决定。

### 13.1 内容怎么挂

| 方式 | 用法 |
|---|---|
| 默认 | 未注册时用 `RecordFlatDetail`（DETAIL 平铺） |
| 注册组件 | `registerRecordView('capacity.company', MyComp)` |
| RecordEntity | `registerRecordView('…', defineRecordEntityView(config))` |
| Slot | `<SchemaView>#record-drawer` 完全自定义 |

```ts
import { registerRecordViews } from '@modoor/views/RecordDrawer'
import { defineRecordEntityView } from '@modoor/views/RecordEntity'

registerRecordViews({
  'capacity.company': defineRecordEntityView({
    head: { title: 'basic.name', subtitle: 'basic.uukey', badge: 'basic.status' },
    tabs: [{ id: 'overview', label: '概要', kind: 'fields', fields: [...] }],
    actions: [{ id: 'edit', label: '编辑', action: 'record.edit' }],
  }),
})
```

`RecordEntity` 自身是组件（head + body tabs + foot），也可用 `#head` / `#body` / `#foot` slot 覆盖。  
后端只提供 record 数据，不声明抽屉布局。

### 13.2 路由与 Menu

_（独立详情页：空）_

### 13.3 详情与列表的数据一致性

以 DETAIL input / search 实时拉取为准。

### 13.4 深链与权限

_（独立详情页深链：空）_

---

## 14. Record API 一览（模块应对齐）

| 能力 | Endpoint | 说明 |
|---|---|---|
| Schema | `POST /api/record/schema` | 列表投影 |
| Search | `POST /api/record/search` | 分页查询 |
| Input | `POST /api/record/input` | 表单投影 |
| Upsert | `POST /api/record/upsert` | 新建/更新 |
| Delete | `POST /api/record/delete` | 按业务键删除 |

前端封装：`@modoor/hooks`（`fetchSchema` / `searchRecords` / …）。  
UI 组件：`@modoor/widget`（`SchemaTable` / `RecordDialog` / `FilterPanel` / `DateRange`），列表页 `@modoor/views`（`SchemaView`）。

---

## 15. 清单：新模块最小交付

- [ ] `module.yaml`（ui-web / menus / ability / i18n）  
- [ ] `domain.py` + `adapters.py`（search / upsert / delete / refers；编号分配）  
- [ ] `models/index.json` + 每实体 `config` / `tables` / `inputs`  
- [ ] `webui.py` + `webui` 路由（Page + Tabs）  
- [ ] SERIALNO `constant`/`counting` 与列表展示业务号  
- [ ] 需要时的默认 `query` / `filters` / 领域 clicks→Dialog  
- [ ] （建议）`migrations/`、totals、tools/skills 覆盖  
- [ ] 详情页：暂不要求（见 §13）

---

## 16. 与平台契约的已知偏差（Fleet 现状）

| 项 | 说明 |
|---|---|
| menus `path` vs 契约 `route` | 现多用绝对 path；新模块优先相对 `base` 的 route |
| OPTIONAL `dictKey` | Fleet 多用内联 `options`；全局字典场景再用 dictKey |
| migrations | Fleet 尚未单列 migrations；靠 ORM create + `_ensure_columns` |
| MCP tools | 远少于 UI 实体；属有意收窄 |
| totals | 管道有、模块未聚 |

新模块应优先**消除**上表偏差，而不是复制偏差。

---

## 修订

| 版本 | 说明 |
|---|---|
| 0.1 | 初稿：自 Fleet 抽取 Module / Entity / Tabs / Action / Query / Filter / Menu / Page / Dialog / Schema / Result / Total；详情页留空 |
| 0.2 | Query RCT/FTR 对齐 option-library/search（`RECENT_3_MONTH` 等 token）；废弃 `3_MONTHS` 缩写 |
| 0.3 | `OPTIONAL` + `extra.computed`：落库派生枚举的简写约束（隐含 `editable: NEVER` + `implicit`） |
