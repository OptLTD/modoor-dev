# Module 契约（围绕期望设计）

> 依据 [`EXPECTATIONS.md`](./EXPECTATIONS.md)：  
> **当前**对外交付是 **Skill + MCP（给其他 AI）**；自有 Chat / 编排 / Mobile Shell 后置。  
> 契约与实现均为自研；调用上下文：必填 `tenant` / `user_id`，可选 `team_id`。  
> 本文规定 Module 必须提供的契约。整合见 [`AI_SYSTEM_PLAN.md`](./AI_SYSTEM_PLAN.md)。

---

## 1. 定位

```text
Module（契约包）—— 含仓库内模块与 external 运行时注册
  ├── 声明（manifest / module.yaml）
  ├── 数据契约（models / migrations；外部可用 artifacts.models）
  ├── Tool 导出（exports.tools + artifacts.tools）
  ├── Skill 导出（exports.skills + artifacts.skills）
  ├── 安全契约（ability / risk）
  ├── UI（ui-web 本阶段；ui-app 后置）
  ├── 可选事件
  └── 测试
           │
           ▼  本项目（能力层 / 整合 = AI-first 注册中心）
     Registry → MCP Server（本地 tools + 外部 artifacts 挂成同名 tools）
              + Skill Catalog（本地 md + 外部 skill artifacts）
           │
           ▼
     外部 AI / MCP 宿主（当前）
```

**分工：**

| 谁 | 导出 / 发布什么 |
|---|---|
| **Module** | **Tools**（必）+ **Skills**（必）+ **Menus**（PC Shell）+ 可选 **ui-web** + models/ability… |
| **整合层** | 把 tools 编成 MCP；组装 PC Shell；**按需**从 models 派生 Resources |

**Module 不直接对接外部 AI。**  
**默认不要求模块导出 `resources` / `prompts`。**

---

## 2. 目录契约（建议形态）

```text
builtin/<id>/ 或 addon/<id>/
  module.yaml           # 必填：清单
  models/               # 必填（可空）：实体（整合层可据此派生只读描述）
  migrations/           # 有模型变更则必填
  tools/                # 可选：无 AI tools 时可空（纯 UI demo 等）
  skills/               # 有 tools 则建议有 Skill
  ability/              # 能力点与默认角色映射
  ui/                   # 可选：后端 JSON API（register）
    web.py
  # PC 壳内置视图：webui/src/views/<id>/（routes.ts + ModuleShell）
  events/               # 可选
  private/              # L2：禁止出现在 exports.tools
  tests/
```

命名空间：对外 ID 使用 `<module_id>.<name>`，全局唯一。

> 目录不必再设 `mcp/resources`、`mcp/prompts`。若极少数模块有不可派生的只读文档，可用 `docs/` 或后续扩展，不作为默认契约。

### 2.1 UI：`ui-web`（本阶段）与 `ui-app`（后置）

| 字段 | 阶段 | 含义 |
|---|---|---|
| `ui-web` | **现在** | PC Web Shell（Brand / Nav / 模块前端入口） |
| `ui-app` | **以后** | 原生 / 移动 App 壳与能力；本阶段不实现，见 [`EXPECTATIONS.md`](./EXPECTATIONS.md) |

`ui-web` **可选**。模块可以没有前端。有前端时：**Master 只认运行时入口**，由模块的 `resolve_entry` 动态返回（template / 静态目录 / `npm run dev` URL 均可）。

#### `ui-web.kind`（Manifest 声明「有没有 / 哪一类」）

| kind | 含义 | 模块提供 | Master 行为 |
|---|---|---|---|
| （省略 / `none`） | 无前端 | — | 不出现在可打开应用列表（仍可有 tools） |
| `app` | 模块自有前端 | **`resolve_entry`（必）** + 可选 `webui/` / templates | 按返回的 `mode` 挂载或跳转 |
| `external` | 真外域独立应用 | 注册中心 `entry_url`；可选 yaml 兜底 | ticket 跳转 |

> 登录由平台 **template**（`/login`）提供，不设根目录 SPA。遗留 `constant` / `built-in` / `kind: template` 解析时视同 `app`。

#### 入口解析：`resolve_entry`（正式契约）

路径约定：`builtin/<id>/webui.py` 或 `addon/<id>/webui.py`（导出 `resolve_entry` + `register`）。

```python
# builtin/<id>/webui.py 或 addon/<id>/webui.py
from modoor.web.entry import EntryContext, WebEntry

def resolve_entry(ctx: EntryContext) -> WebEntry | None:
    """返回此刻前端入口；None = 本请求无 UI。"""
    ...

def register(app, kit) -> None:
    """挂载本模块 HTTP 路由（通常委托 route.py）。"""
    ...
```

`WebEntry`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `mode` | `url` \| `static` \| `template` | 交付形态 |
| `target` | `str` | 见下表 |
| `base` | `str` 可选 | 挂载前缀；缺省用 `ui-web.base` |

| `mode` | `target` 示例 | Master 做什么 |
|---|---|---|
| `url` | `http://127.0.0.1:5175/` | 开发态代理 / 跳转（`npm run dev`） |
| `static` | `builtin/wiki/webui/dist` | 同源挂载静态目录 |
| `template` | `wiki/home.html` 或已 register 的路由前缀 | 服务端 template 渲染 |

解析优先级（固定）：

```text
1. resolve_entry(ctx)          ← 正式、可按 env/tenant 切换
2. registry live entry_url     ← external / 热注册
3. ui-web.entry（yaml 兜底）   ← 仅建议 external 静态默认
4. 无 → 无前端
```

`EntryContext` 至少含：`module_id`、`env`（dev/prod）、`tenant_id`（可选）、`settings`。  
**返回的是入口，不是 Vue 组件树**；模块内部路由由模块自己负责。

示例（同一模块三种交付，按环境切换）：

```python
def resolve_entry(ctx: EntryContext) -> WebEntry | None:
    if ctx.env == "dev":
        return WebEntry(mode="url", target="http://127.0.0.1:5175/", base="/wiki")
    dist = ctx.module_root / "webui" / "dist"
    if dist.is_dir():
        return WebEntry(mode="static", target=str(dist), base="/wiki")
    return WebEntry(mode="template", target="wiki/home.html", base="/wiki")
```

共享前端放在仓级 `shared/`，**按组件完整目录组织**（类似 Element UI：用哪个就进哪个目录拿完整实现）：

```text
shared/
  widget/            # 基础控件和复合组件
    SelectBox/
    DateRange/
    FilterPanel/
    SchemaTable/     # 列表复合组件
    SchemaForm/      # 字段表单，不含弹窗
    SchemaSheet/     # 表格复合组件
    ChartGrid/       # 看板格子，只渲染已准备好的卡片
  views/             # 会请求接口的界面
    SchemaView/      # 标准列表页（tabs；单 tab = 当前页）
    RecordDialog/
    RecordDrawer/
    RecordEntity/
    TableDrawer/
    ChartView/       # 看板页：取数和格子位置
    ShellFrame/
  hooks/             # 跨组件共享：http、record client、fieldMeta、dialog…
```

| 包 | 放什么 | 不放什么 |
|---|---|---|
| `widget/<Name>/` | 基础控件，以及由它们拼成的复合组件（`SchemaTable`、`SchemaSheet`） | 业务页 |
| `views/<Name>/` | 会请求接口的界面（如 `SchemaView`） | 基础控件、业务页 |
| `hooks/` | 多组件共用的非 UI 能力 | 某个组件的私有逻辑 |

用法示例：

```ts
import { SchemaTable } from '@modoor/widget/SchemaTable'
import { SchemaSheet } from '@modoor/widget/SchemaSheet'
import { SchemaView } from '@modoor/views/SchemaView'
import { RecordDialog } from '@modoor/views'
```

模块 `webui`、Master shell 都依赖这些包；**模块之间不互相 import 页面**。

#### Manifest 示例

```yaml
ui-web:
  kind: app                 # | external | none
  label: Wiki
  base: /wiki               # 模块独占前缀；公开挂载为 /mod/wiki
  home: /wiki
  # entry: https://...      # 可选兜底；正式入口以 resolve_entry 为准

exports:
  tools: [...]
  skills: [...]
  menus:                    # 相对 base
    - id: wiki.pages
      label: Pages
      route: .
      seqno: 10
```

| 字段 | 谁用 | 说明 |
|---|---|---|
| `ui-web.base` | 壳 / 挂载 | 模块独占前缀（如 `/wiki`）；公开 URL = `/mod` + base |
| `ui-web.seqno` | 壳下拉 / 工作台 | 模块排序（越小越前）；缺省 `1000`；建议 builtin `0–100`，业务 addon 按域段分配 |
| `exports.menus[].route` | 壳 | 相对 `base` |
| `exports.menus[].seqno` | 壳 Nav | 菜单排序（越小越前）；缺省 `100` |
| `ui-web.entry` | 兜底 | 可选；**不替代** `resolve_entry` |
| ~~`built-in` / `constant`~~ | — | 遗留；解析视同 `app` |
| ~~`path_prefix` / 菜单绝对 `path` / `home`~~ | — | 废弃；`base` 替代 `path_prefix`，解析层短期兼容 |

**推荐使用顺序：**

```text
1. app + resolve_entry ← template / static / vite-dev
2. packages（widget / hooks）← Element 风格复用
3. external            ← 外域；registry 或 resolve_entry → url
```

#### `app`

- 模块可选 `webui/`（Vue/静态）或仅 templates
- **必须**实现 `resolve_entry`（或明确 `None` + 说明）
- JSON API 仍可经模块根 `webui.register` / `route.py` 挂到主进程
- SchemaTable 等 CRUD 在模块自己的 `webui/` 里用 `@modoor/widget` 拼

#### `external`

- 真独立进程 / 外域；Master 不参与渲染
- 入口：`resolve_entry` → `mode:url` **或** registry `entry_url`
- 强烈建议应用内具备模块切换、logout
- 示例：`external/board`、`external/pulse`

壳辅助 API：

| API | 用途 |
|---|---|
| `GET /api/apps/catalog` | `tenant` + `profile` + `modules`（含 **解析后的 entry**）+ `exports`；支持 ticket |
| `GET /api/shell/modules` | 同上，需 session（壳内切换器用） |
| `GET /api/apps/exports` | 外部应用聚合能力 |
| `POST /api/apps` | 注册 external（body: `id` + `entry_url`…） |
| `POST /api/apps/{id}/heartbeat` | 心跳 |
| `GET /go/<module_id>` | 解析 entry 后跳转 / 挂载 |
| `GET\|POST /logout` | 结束 session |

禁止为 UI 旁路写库；写操作仍走 domain / tools。

---

## 3. Manifest 契约（`module.yaml`）

必填字段：

| 字段 | 含义 |
|---|---|
| `id` | 模块 ID（稳定、小写、唯一） |
| `version` | semver |
| `depends` | 依赖模块列表（拓扑可解、无环） |
| `summary` | 给人 / Router 的短描述 |
| `exports.tools` | 显式 L1 tool 名单（可 `[]`；**有 AI 能力时必填非空**） |
| `exports.skills` | 显式 Skill 名单（可 `[]`） |
| `ability` | 本模块能力点（可 `[]`） |

可选：`events`、`category`、`risk_default`、`ui-web.*`、`exports.menus`、`exports.views`、`exports.actions`。  
**不要求** `exports.resources` / `exports.prompts`。  
**本阶段不实现** `ui-app`（见 Expectations）。

PC Shell（`ui-web`）：

- `ui-web.kind` / `ui-web.label` / **`ui-web.base`**
- **`resolve_entry`**：`app` / 需要动态入口的模块正式入口；见 §2.1
- `exports.menus[]`：`route`（相对 base）
- `ui-web.entry`：可选 yaml 兜底（不替代 `resolve_entry`）
- 废弃：菜单绝对 `path`、`ui-web.home` / ~~`path_prefix`~~（用 `ui-web.base`）；`kind: template` / 壳内硬编 `built-in` views（过渡）

规则：

- **未列入 `exports.tools` 的 tool 一律 L2**，不得挂到 MCP
- Skill 只能引用已 export（含 depends 模块）的 tools
- `depends` 未满足则拒绝安装
- 升级只允许通过 `migrations/` + version bump

---

## 4. MCP 侧契约（谁提供什么）

应用/整合层负责 **MCP Server 形态**；模块只保证 **Tool 语义**。

```text
Module.tools  ──编译──▶  MCP Tools          （必有）
Module.models ──派生──▶  MCP Resources      （整合层可选做）
Module.skills ──发布──▶  Skill Catalog      （给外部 AI 加载；不必再做 MCP Prompts）
```

### 4.1 Tool（模块必导出）

每个 tool 必须声明：

| 项 | 要求 |
|---|---|
| `name` | `<module>.<action>` |
| `description` | 给 Agent 的用途说明（稳定、无实现细节） |
| `input_schema` | JSON Schema（严格） |
| `output_schema` | JSON Schema（建议必填） |
| `ability` | 执行所需能力点 |
| `risk` | `low` \| `medium` \| `high` |
| `idempotency` | 是否幂等；非幂等应支持 idempotency key（建议） |
| `side_effects` | `read` \| `write` \| `destructive` |

行为约定：

- 成功：返回结构化 result（符合 output_schema）
- 需确认（高风险）：返回 `status=needs_confirmation` + confirmation payload（Canvas 可渲染）
- 失败：稳定 error code（如 `permission_denied` / `validation_error` / `not_found` / `conflict`）
- **禁止** tool 内直接「再暴露」未 export 的私有函数给 Agent

### 4.2 Resources / Prompts（默认不由模块导出）

| MCP 原语 | 默认来源 | 模块是否要写 |
|---|---|---|
| **Tools** | `exports.tools` | **要** |
| **Resources** | 整合层从 `models` + ACL 派生（如 model/record 描述） | **不要**（默认） |
| **Prompts** | 用 **Skill** 替代 SOP；整合层可不实现 MCP Prompts | **不要** |

说明：

- Resource 若需要：由整合层统一提供只读面（schema/describe），避免每个模块重复声明 `model://…`
- Prompt 与 Skill 重叠时优先 Skill，防止两套 SOP
- 将来若有「无法从 model 派生」的特例，再开可选扩展；不进入 MVP 契约

### 4.3 与 MCP 服务器的映射（整合层职责）

| 策略 | 说明 |
|---|---|
| **A. 单聚合 MCP Server** | 一个 endpoint，聚合各模块 tools（**已决**） |
| **B. 每 Module 一个 MCP Server** | 边界清晰；宿主需多 server |

无论 A/B：**模块只交 tools（+ skills）**；MCP 打包与 list/call 由整合层完成。

---

## 5. Skill 侧契约（Module → Skill Catalog）

Skill = **怎么用 MCP 完成一类任务**，不是第二套 API。

### 5.1 单个 Skill 必须包含

| 项 | 要求 |
|---|---|
| `id` | `<module>.<skill_name>` |
| `title` / `summary` | 路由与展示用 |
| `when_to_use` | 适用意图 / 触发条件 |
| `steps` | 有序步骤（可含分支） |
| `tools` | 引用的 tool 名列表（必须 ⊆ 本模块或 depends 的 `exports.tools`） |
| `confirmations` | 哪些步骤必须 Human-in-the-loop |
| `禁忌 / 边界` | 明确不要做什么 |

（不再要求 Skill 声明 MCP resources；需要模型说明时，依赖整合层 describe 或 `get_*` 类 read tools。）

建议文件：`skills/<skill_name>.md` + 可选 `skills/<skill_name>.yaml` frontmatter。

### 5.2 Skill 规则

- Skill **不得**要求调用未 export 的 tool
- Skill **不得**指导 Agent「直接改库 / 猜表结构」
- 跨模块流程：允许 Skill 引用 **depends 已提供** 的外模块 tool；或拆成多 Skill 由上层编排
- AI 生成的 Skill 必须同样满足本契约，并进入版本管理

---

## 6. 数据与安全契约

### 6.1 Model

- 模型元数据可供**整合层**生成只读描述（若实现 Resources/describe）
- 字段变更走 migrations；破坏性变更需 major version + 升级说明
- `@extend` 他模块模型时：必须 `depends` 对方，并声明 extend 点
- 只读查询优先用显式 read tools（如 `sale.get_order`），不依赖模块自建 Resource 导出

### 6.2 Ability

- 每个 L1 Tool 绑定至少一种 ability
- 整合层在 MCP `call` 前强制校验；校验基于 **ctx**（`tenant`、`user_id`，及可选 `team_id`）
- L0 Meta tools 使用独立高权限（如 `meta.module.manage`）

### 6.3 调用上下文（ctx）

整合层注入的固定上下文（与鉴权映射结果一致）：

| 字段 | 必填 | 含义 |
|---|---|---|
| `tenant` | 是 | 租户 |
| `user_id` | 是 | 操作用户 |
| `team_id` | 否 | 团队 / 组织单元；小企业无多组织时可省略 |

整合层注入的上下文（与鉴权映射结果一致）。未传 `team_id` 时按租户级处理。

Tool 实现只消费 ctx，不得自行解析凭证或旁路租户隔离。

### 6.4 审计

- 所有 L1 Tool 调用由整合层记审计：ctx（tenant / user_id / 可选 team_id）/ when / tool / args摘要 / result status
- Module 可通过 events 补充领域事件，但不替代审计

---

## 7. L0 Meta 作为特殊 Module

`meta`（或 `base_meta`）本身也是 Module，导出的是「造模块」的 MCP Tools + Skills，例如：

- Tools：`meta.define_model`、`meta.define_tool`、`meta.define_skill`、`meta.install_module`…
- Skills：`meta.author_minimal_module`（如何安全生成并安装一个最小模块）

业务 Module 不实现 L0；只消费 Kernel，并导出 L1。

---

## 8. 契约自检清单（安装前）

安装 / 升级前整合层校验：

- [ ] `module.yaml` 字段完整，depends 可解
- [ ] `exports.tools` ⊆ 实际实现且均可生成 JSON Schema
- [ ] 每个 export tool 有 ability + risk
- [ ] 每个 Skill 引用的 tools 均在允许集合内
- [ ] `private/` 下无符号出现在 exports
- [ ] migrations 与 version 一致
- [ ] 测试：至少一个 skill 路径的集成测试（可 mock Agent）

不通过则拒绝安装。

---

## 9. 最小示例（销售模块导出面）

```yaml
# addon/sale/module.yaml（示意）
id: sale
version: 0.1.0
depends: [base, partner, product]
summary: 销售订单与确认

exports:
  tools:
    - sale.create_order
    - sale.confirm_order
    - sale.get_order
  skills:
    - sale.create_and_confirm_order

ability:
  - sale.order.read
  - sale.order.write
  - sale.order.confirm

ui-web:
  kind: app
  label: Sale
  base: /sale
  home: /sale
```

Skill `sale.create_and_confirm_order` 只编排上述 tools，并在 `confirm_order` 处置 risk=high 确认。

---

## 10. 一句话

> **Module 默认对外契约 = Manifest + Tools + Skills + Ability + Migrations（+ 可选 ui-web）。**  
> 业务实现（models / domain）放在 `addon/<id>/` 或 `builtin/<id>/`，不进能力层核心包。  
> MCP Server 由整合层组装；Resources/Prompts 非模块必选项（SOP 用 Skill，只读描述可由整合层派生）。
