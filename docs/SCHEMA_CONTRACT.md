# Schema 契约（业务模型约定）

> 约定 Module 内**业务模型的 UI / 解释层**如何声明字段、分组、关联与视图元数据。  
> 设计参考 option-worth `data/bundles`（config / tables / inputs），适配 Modoor 的 Module + `ability` + `ui-web`。  
> **不替换**现有 `domain.py`（ORM / 落库）；二者**双写并存**，职责不同（见 §0）。

---

## 0. 双层约定（domain + schema）

AI-first 主路径是 **读写与分析**（Tools / Skills / MCP）；**授权与危险操作确认仍靠人**（ability + `needs_confirmation` + 宿主确认 UI）。

| 层 | 载体 | 负责什么 | 不负责什么 |
|---|---|---|---|
| **底层数据** | `domain.py` + `migrations/` | 表结构、约束、事务、tenant 隔离、领域不变量 | 列表长什么样、表单怎么排、给人/AI 的字段说明 |
| **UI + Schema 解释** | `models/**/config|tables|inputs` | 字段语义、分组、字典/关联、列表与表单约束、供人与 AI **理解模型** | 替代 ORM；不单独成为写库通道 |

```text
         ┌─ domain.py ─────────── 落库真相（SQLAlchemy）
Module ──┤
         └─ models/*/config.json ─ 解释与 UI 约束（给人 / AI / 模块 webui）
                      │
                      ├─ tables.json / inputs.json → ui-web 展示与录入边界
                      └─ describe / Skill 上下文   → AI 读懂「有什么字段、含义是什么」
```

**双写原则：**

1. 改业务字段时：**domain 与 config 一起改**（物理列 ↔ schema 字段键对齐）。  
2. Tool 的 input/output 以 **domain 行为**为准；schema 用于说明与 UI，二者语义应对齐，但不互相生成对方（本阶段不强求 codegen）。  
3. `tables` / `inputs` 约束的是 **人机界面与可编辑边界**，不是 MCP 鉴权；鉴权仍是 ability + 人工确认。  
4. Agent 写库仍只走 `exports.tools`；可读 schema / describe 辅助分析，**禁止**按 schema 直连猜表。

---

## 1. 在 Module 中的位置

```text
addon/<module_id>/ 或 builtin/<module_id>/
  module.yaml
  domain.py                    # 底层数据约定（已有；本契约不取代）
  models/                      # UI + schema 解释（本文件约定）
    <model_short>/             # 建议与模型短名一致，如 order /
      config.json              # 模型解释：model / groups / fields / clicks
      tables.json              # 可选：列表 UI / 查询约束
      inputs.json              # 可选：表单 UI / 录入约束
      seeds.json               # 可选：安装种子数据
    index.json                 # 可选：本模块模型清单
  migrations/
  tools/
  skills/
  ...
```

| 文件 | 作用 |
|---|---|
| `domain.py` | **落库与领域逻辑**（保持现状） |
| `config.json` | **schema 解释核心**：标识、分组、字段含义、动作语义 |
| `tables.json` | 列表：展示字段、默认筛选、工具栏动作（UI + 查询边界） |
| `inputs.json` | 表单：布局、默认值、可编辑边界（UI + 录入边界） |
| `seeds.json` | 首次安装示例数据（已有行则跳过） |
| `models/index.json` | 模块内模型注册（uukey → 路径 / 级别） |

模型对外解释 ID（**uukey**）建议：`<module_id>.<entity>`，如 `sale.order`。  
与 domain 主键（常为 UUID `id`）可并存：`basic.uukey` 是业务编号；技术主键仍由 domain 管理。

外部应用若导出 models，放在注册 `artifacts.models[]` 中，字段语义与本文 `config.json` 的 `fields` 对齐（可简化；完整 schema 可用 `schema_url`）。

---

## 2. `config.json` 结构

每个业务模型至少包含四块：`model`、`groups`、`fields`、`clicks`。

```json
{
  "model": {
    "uukey": "sale.order",
    "title": "销售订单",
    "brief": "",
    "source": "sale_orders",
    "search": "sale_orders",
    "extra": { "constant": "SO", "counting": 5 }
  },
  "groups": {
    "basic": {
      "uukey": "basic",
      "title": "基础信息",
      "gtype": "FLATTEN",
      "model": "sale.order",
      "seqno": 0,
      "extra": {}
    }
  },
  "fields": {
    "basic.uukey": { "...": "见 §3" },
    "basic.utime": { "...": "见 §3" },
    "basic.status": { "...": "见 §3" }
  },
  "clicks": {
    "create": {
      "uukey": "create",
      "label": "新增",
      "ctype": "button",
      "action": "record.create",
      "seqno": 1
    }
  }
}
```

### 2.1 `model`

| 字段 | 要求 | 说明 |
|---|---|---|
| `uukey` | 必填 | 模型 ID，`<module>.<entity>` |
| `title` | 必填 | 显示名 |
| `brief` | 可选 | 简介 |
| `source` | 建议 | 物理表名 / 存储标识 |
| `search` | 可选 | 搜索/列表投影表，默认同 `source` |
| `extra.constant` | 建议 | 流水号前缀，2–4 位大写 |
| `extra.counting` | 建议 | 流水号数字位数 |

### 2.2 `groups`

| 字段 | 说明 |
|---|---|
| `uukey` | 分组键，如 `basic` |
| `title` | 显示名 |
| `gtype` | `FLATTEN` 字段摊在主记录上；`GROUPED` 收成一个对象。重复多条用 `extra.multiple`，表单用表格呈现（一行一条） |
| `model` | 所属模型 uukey |
| `seqno` | 排序（可从 0 起） |

单模型通常先有一个 `basic` 分组；复杂表单再拆组。

### 2.3 `fields`

字段键使用 **`{group}.{field}`**，如 `basic.status`。每项建议包含：

| 字段 | 说明 |
|---|---|
| `field` | 物理/逻辑列名 |
| `ftype` | 字段类型（§4） |
| `group` | 所属分组 uukey |
| `index` | 稳定索引键，通常等于字段键 |
| `label` | 显示标签 |
| `seqno` | 组内/全局排序 |
| `using` | RELATION 时目标模型 uukey |
| `extra` | 约束与 UI 提示（required / editable / dictKey / relation…） |

`field` 在所属分组里已经能看懂，就不要再重复分组语义。`label` 仍用完整中文；短名只用于 `field`、字段键和 sample 里的键。`basic.uukey` / `basic.utime` / `basic.status` 是固定键，不参与缩写。选项 `uukey` 保持可读，不跟着字段短名缩。

- 分组已经表达的词去掉：`audits` 下用 `type` / `status` / `expire` / `name` / `file` / `reason`，不要 `cert_type` / `audit_status` / `expire_date` / `holder_name` / `file_url` / `reject_reason`。
- 一个词已经完整就保持，如 `vehicle`、`remark`。
- 字段名里的长角色词缩写：`driver` → `dr`，如 `photos.dr_license`。
- 分组键按这组明细在记什么来命名。审核逐条记录用 `audits`；证件日期用 `dates`；证件图片用 `photos`。证件号码和行驶证正文放在 `basic`。某一份证件自己成套时单独分组，如道路运输证用 `permit`，组内去掉 `permit` 前缀。

### 2.4 `clicks`

动作按钮（列表/表单工具栏）。建议至少具备业务需要的 create / delete；可映射到 Module `exports.actions` 或 tools。

| 字段 | 说明 |
|---|---|
| `uukey` | 动作键 |
| `label` | 显示名 |
| `ctype` | 如 `button` |
| `action` | 语义动作，如 `record.create` / `record.delete` / `record.export` |
| `seqno` | 排序 |

---

## 3. 核心字段约定（uukey / utime / status）

每个业务模型应在 `basic` 分组**显式定义**下列字段（有状态流转则必须含 status），并固定靠前：

| seqno | 字段键 | ftype | 说明 |
|---|---|---|---|
| 1 | `basic.uukey` | `SERIALNO` | 业务编号 |
| 2 | `basic.utime` | `DATETIME` | 业务主时间，label 跟模型走（开单、下单、登记等），可修改。不要写成「创建时间」 |
| 3 | `basic.status` | `OPTIONAL` | 业务状态（有状态机时**必填**） |
| 4+ | 其他 | — | 名称、关联、金额、备注等 |

另：多租户隔离字段 `tenant`（及可选 `team_id`）由整合层 / ORM 层保证，**不必**出现在业务 `fields` 展示里，但存储与查询必须带 ctx。

### 3.1 `basic.uukey`

```json
"basic.uukey": {
  "field": "uukey",
  "ftype": "SERIALNO",
  "group": "basic",
  "index": "basic.uukey",
  "label": "订单编号",
  "seqno": 1,
  "extra": {
    "required": true,
    "editable": "INSERT",
    "constant": "SO",
    "counting": 5
  }
}
```

- 流水号 = `constant` + 零填充数字（如 `SO00001`）。
- 前缀 2–4 位大写，**模块内唯一**，建议全局不冲突。

### 3.2 `basic.utime`

```json
"basic.utime": {
  "field": "utime",
  "ftype": "DATETIME",
  "group": "basic",
  "index": "basic.utime",
  "label": "下单时间",
  "seqno": 2,
  "extra": { "editable": "ALWAYS", "dataType": "DATETIME" }
}
```

只要日期时：`extra.datetime: "ONLYDATE"`。

`basic.utime` 是业务时间，默认可改（`editable: ALWAYS`）。不要把它标成「创建时间」。

创建时间是数据引擎写入的 `basic.created_at`，不在 `config.json` 里声明。引擎字段（如 `basic.created_at`）由引擎维护，模型配置不表现。

### 3.3 `basic.status`

```json
"basic.status": {
  "field": "status",
  "ftype": "OPTIONAL",
  "group": "basic",
  "index": "basic.status",
  "label": "状态",
  "seqno": 3,
  "extra": {
    "required": true,
    "editable": "ALWAYS",
    "dictKey": "global:sale.order.status"
  }
}
```

无状态概念的模型可省略；有流转则 `required: true` 且必须挂 `dictKey`。

---

## 4. `ftype` 常用类型

| ftype | 用途 |
|---|---|
| `SERIALNO` | 业务编号 |
| `SUBJECT` | 主题/名称（列表主文案） |
| `STRINGS` | 普通字符串；长文可用 `extra.dataType: "LONGTEXT"` |
| `NUMERIC` | 数值；`extra.precision` / `dataType: DECIMAL\|INTEGER` |
| `DATETIME` | 日期时间 |
| `OPTIONAL` | 字典/枚举下拉 |
| `RELATION` | 关联其他模型 |

### RELATION

```json
"basic.partner_id": {
  "field": "partner_id",
  "ftype": "RELATION",
  "group": "basic",
  "index": "basic.partner_id",
  "label": "客户",
  "seqno": 4,
  "using": "base.partner",
  "extra": {
    "editable": "ALWAYS",
    "relation": "base.partner",
    "dataKey": "basic.uukey",
    "textKey": "basic.name"
  }
}
```

- `using` / `extra.relation`：目标模型 uukey（目标模块须在 `depends` 中或本模块内）。
- `dataKey` / `textKey`：存值字段与显示字段。

### `extra.editable`

| 值 | 含义 |
|---|---|
| `INSERT` | 仅新建可改 |
| `ALWAYS` | 始终可改 |
| `NEVER` | 只读 |

### `dictKey`

格式：`global:<domain>.<name>`，如 `global:sale.order.status`。  
字典内容可由模块 `dicts` / 种子数据提供；整合层负责租户级字典表。

---

## 5. `seqno` 规则

1. `groups`、`fields`、`clicks` 均应设 `seqno`（JSON 无序）。
2. 字段：`uukey=1`，`utime=2`，`status=3`（若有），业务字段从 4 递增。
3. 同一模型内 `seqno` 不重复。
4. 调整顺序时同步 `tables.json` / `inputs.json` 的字段列表。

推荐业务字段顺序：名称/标题 → 分类 → 关联 → 金额/数量 → 备注。

---

## 6. 视图：`tables.json` / `inputs.json`

`tables` / `inputs` 是对 **UI 与人机数据边界** 的约束（展示哪些列、默认筛什么、表单可改什么），  
**不是** MCP 授权模型。AI 侧读写分析走 tools；授权与高风险确认仍靠 **ability + 人**。

供模块 `webui`（及 template 自研页）消费；对 AI 可作为「人通常怎么看/怎么填」的说明，可选。

### tables（列表）

```json
{
  "default": {
    "uukey": "default",
    "title": "列表",
    "fields": ["basic.uukey", "basic.status", "basic.name"],
    "clicks": ["create", "delete", "export"],
    "query": {},
    "extra": {}
  }
}
```

### inputs（表单）

```json
{
  "default": {
    "uukey": "default",
    "title": "表单",
    "preset": { "audit.status": "pending" },
    "fields": [".*"],
    "hidden": ["audit.*"],
    "groups": ["basic"],
    "clicks": [],
    "extra": {}
  },
  "audit": {
    "uukey": "audit",
    "title": "审核",
    "groups": ["audit"],
    "fields": ["audit.*"],
    "clicks": [],
    "extra": {}
  }
}
```

约定：

- `fields` / `hidden` 支持通配（如 `audit.*`、`.*`）；项应对应 `config.json` 字段键。
- **审核字段**放在 `audit` 分组：基础表单用 `hidden: ["audit.*"]`（或 `groups` 不含 audit）隐藏；审核动作单独 `using=audit`。
- `preset` 可在隐藏字段上设默认值（如新建默认 `audit.status=pending`）。
- 由动作迁移改写的字段设 `implicit: true`，不出现在普通表单。例如审核状态、证照状态、核对状态、启用停用。动作按钮另开表单收集原因；原因字段不设 `implicit`，只放在该动作的 input 里。

---

## 7. 与 domain / Tools / Ability / UI 的关系

```text
domain.py + migrations     → 落库真相、事务、tenant
models/*/config.json       → 字段解释（给人 / AI describe）
models/*/tables|inputs     → UI 与录入/列表约束
exports.tools + Skills     → AI 读写分析主路径
ability + confirmation     → 人授权 / 高风险确认
```

规则：

- **双写**：domain 与 config 语义对齐，改字段两边都改；不互相替换。  
- Schema 解释「有什么、什么意思」；Tool 执行「读/写/分析」；Ability/人决定「能不能」。  
- Agent **不得**按 schema 猜表改库；写操作只走 `exports.tools`。  
- `@extend` 他模块模型：必须 `depends`，并在 schema 中声明扩展点（后置细化）。

---

## 8. 最小示例（`sale.order` 示意）

```json
{
  "model": {
    "uukey": "sale.order",
    "title": "销售订单",
    "source": "sale_orders",
    "extra": { "constant": "SO", "counting": 5 }
  },
  "groups": {
    "basic": {
      "uukey": "basic",
      "title": "基础信息",
      "gtype": "FLATTEN",
      "model": "sale.order",
      "seqno": 0
    }
  },
  "fields": {
    "basic.uukey": {
      "field": "uukey",
      "ftype": "SERIALNO",
      "group": "basic",
      "index": "basic.uukey",
      "label": "订单编号",
      "seqno": 1,
      "extra": { "required": true, "editable": "INSERT", "constant": "SO", "counting": 5 }
    },
    "basic.utime": {
      "field": "utime",
      "ftype": "DATETIME",
      "group": "basic",
      "index": "basic.utime",
      "label": "下单时间",
      "seqno": 2,
      "extra": { "editable": "ALWAYS" }
    },
    "basic.status": {
      "field": "status",
      "ftype": "OPTIONAL",
      "group": "basic",
      "index": "basic.status",
      "label": "状态",
      "seqno": 3,
      "extra": {
        "required": true,
        "dictKey": "global:sale.order.status"
      }
    },
    "basic.partner": {
      "field": "partner",
      "ftype": "SUBJECT",
      "group": "basic",
      "index": "basic.partner",
      "label": "客户",
      "seqno": 4,
      "extra": { "required": true, "editable": "ALWAYS" }
    }
  },
  "clicks": {
    "create": {
      "uukey": "create",
      "label": "新建",
      "ctype": "button",
      "action": "record.create",
      "seqno": 1
    }
  }
}
```

对应 `module.yaml` 中可通过 `exports` / tools 暴露 `sale.create_order` 等；schema 与 tool 参数应对齐。

---

## 9. Checklist（新增模型）

- [ ] `uukey` = `<module>.<entity>`，已写入模块 `models/`（或 external `artifacts.models`）
- [ ] `config.json` 含 `model` / `groups` / `fields` / `clicks`
- [ ] 显式 `basic.uukey`（及按需 `utime` / `status`），seqno 正确
- [ ] RELATION 目标在 depends / 本模块内；dictKey 已规划
- [ ] 流水号 `constant`/`counting` 模块内不冲突
- [ ] 有状态则 `basic.status.required=true`
- [ ] 若走 SchemaTable：补 `tables.json` / `inputs.json`
- [ ] 物理变更有 `migrations/`；写路径仅经 tools

---

## 10. 一句话

> **domain 管落库；schema（config/tables/inputs）管解释与人机 UI 边界；AI 管读写分析；人管授权。双写并存，互不替代。**
