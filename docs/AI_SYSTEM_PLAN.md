# AI-First Capability Layer — 整合项目 Plan（能力层优先）

> 状态：讨论草案  
> **理念**：以可安装 **Module** 为扩展单位，自研契约与实现。  
> **本项目当前职责**：整合 Module，对外发布 **Skill + MCP**（AI 能力层），供**其他 AI** 消费。  
> **当前不做**：自有 AI Chat、AI 编排、终端 Chat/Mobile Shell。  
> 期望见 [`EXPECTATIONS.md`](./EXPECTATIONS.md)；契约见 [`MODULE_CONTRACT.md`](./MODULE_CONTRACT.md)。

---

## 1. 文档怎么读

```text
EXPECTATIONS.md       要什么（先能力层，后 Chat/编排）
        ↓
MODULE_CONTRACT.md    Module 交什么（Skill + MCP 素材）
        ↓
AI_SYSTEM_PLAN.md     本仓做什么（整合 + 对外暴露）
        ↓
PHASE0.md / INTEGRATION.md  实现约定与接入
```

---

## 2. 本项目是什么（当前）

| 是 | 不是（当前阶段） |
|---|---|
| Module Registry / 安装生命周期 | 业务 Chat 产品 |
| **MCP Server 发布层** | Planner / 多 Agent 编排 |
| **Skill Catalog**（可被外部加载） | 自研对话 UI |
| ACL、审计、确认协议 | Mobile/Web Canvas 渲染器 |
| （稍后）L0 Meta Module 宿主 | 终端用户 App |

数据流（当前）：

```text
builtin/* + addon/*  ──install──▶  Registry
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         MCP Server   Skill Catalog  ORM/ACL/Audit
              │            │
              └────────────┤
                           ▼
              外部 AI / MCP 宿主（Cursor、Claude、自建 Agent…）
```

---

## 3. 路线

| 阶段 | 内容 |
|---|---|
| **现在** | 能力层：Module + MCP + Skill + ACL/审计（自有落库） |
| Phase 0 | 自研最小后端 + 一条垂直链，打通「外部 AI → MCP → 落库」 |
| 以后 | 自有 Runtime / Chat / Mobile Shell（复用同一契约，不另起写库 API） |
| 避免 | 先做 Chat 再补能力面 |

---

## 4. 整合层职责（对齐契约）

1. 校验 manifest / exports / skill 引用后才安装  
2. 仅 `exports.*` → MCP list + Skill catalog  
3. `call` 前注入 **ctx**（`tenant` / `team_id` / `user_id`），强制 permission；高风险走 `needs_confirmation` 协议  
4. 对外提供接入说明（endpoint、鉴权、Skill 加载方式）  
5. （后续）托管 `meta` Module（L0）  

MCP 暴露策略（已决）：

- **A. 单聚合 MCP Server**（已选）  
- ~~B. 每 Module 一个 MCP Server~~（当前不做）

---

## 5. 分阶段落地

### Phase 0 — 对外联通

- [x] 选 1 条垂直链：**销售单 create → confirm**（已决）
- [x] 最少一组 MCP Tools + 1 份 Skill（`sale.create_order` / `sale.confirm_order` + 对应 Skill）
- [ ] 用至少一种**外部** MCP 客户端打通（见 `docs/INTEGRATION.md`）
- [x] 确认流协议可演示（即使确认 UI 在客户端侧）；`confirm_order` 为高风险
- [x] 自有最小持久化（SQLAlchemy；PostgreSQL）；每次 call 带齐 ctx
- [x] API Key 鉴权并映射到 `tenant` + `user_id`

### Phase 1 — 能力层 MVP

- [ ] Module 发现 / depends / install
- [ ] exports → MCP 编译
- [ ] Skill Catalog（文件或 HTTP 可拉取）
- [ ] ACL + 审计
- [ ] 示例模块：`base`、`partner`、`product`、`sale`
- [ ] 接入文档

### Phase 2 — 可生成 / 可扩展

- [ ] 按 module 过滤 tool list
- [ ] （可选）整合层从 models 派生 describe/Resources
- [ ] L0 Meta Module（供外部 AI 造模块）
- [ ] UI Schema 仅契约预留

### Phase 3 — 自有体验（后置）

- [ ] 自有 Agent Runtime / Chat
- [ ] Mobile / Web Shell（同一 MCP）
- [ ] 多租户产品化、模块市场

### 明确暂缓（当前）

- 自研 AI Chat、AI 编排  
- Mobile App / Canvas 渲染  
- 热插拔不重启、影子改表、复刻全应用树  

---

## 6. 调用上下文（ctx）— 已决

每次 MCP `call` 由整合层注入（或校验后透传）的上下文：

| 字段 | 必填 | 含义 |
|---|---|---|
| `tenant` | **是** | 租户（多租户隔离根） |
| `user_id` | **是** | 当前操作用户 |
| `team_id` | **否** | 团队 / 组织单元（租户内）；小企业无多组织时可省略 |

规则：

- ACL、审计、确认 token 至少绑定 `tenant` + `user_id`；若请求带了 `team_id`，范围权限按 team 收窄
- 未传 `team_id` 时视为「租户级 / 无组织维度」操作（典型小企业）
- Tool 实现不得自行「猜」当前用户；一律从 ctx 读取
- 鉴权层负责把凭证映射到这些字段后再进入 Registry / Tool

---

## 7. 技术选型

| 层 | 选型 | 备注 |
|---|---|---|
| 能力层语言 | **Python**（已决） | MCP Server 生态成熟 |
| MCP 形态 | **A. 单聚合 MCP Server**（已决） | 一个 endpoint，聚合各模块 tools |
| 鉴权 | **API Key → ctx**（Phase 0 已决） | Key 映射到 `tenant` + `user_id`（及可选 `team_id`）；OAuth/用户委派后置 |
| ORM | **SQLAlchemy 2.x**（已决） | 自有栈 |
| 数据库 | **PostgreSQL**（已决；本仓不支持 SQLite） | |
| 编排 / Chat | — | **当前不做** |
| 移动 | — | **当前不做**；契约可预留 |

---

## 8. 术语（拍板用）

| 说法 | 是什么 | 为什么要选 |
|---|---|---|
| **垂直链** | 一条从头到尾能跑通的业务路径，例如「建客户 → 建产品 → 创建销售单 → 确认」 | Phase 0 不铺全模块，先用**这一条**证明外部 AI 能经 MCP 落库 |
| **MCP A / B** | **A**：整个系统一个 MCP Server，tools 聚合在一起；**B**：每个 Module 各自一个 MCP Server | **已选 A**；宿主只配一个 endpoint |
| **鉴权** | 外部 AI 调用我们 MCP 时如何证明「是谁」，并映射成 ctx | **Phase 0 已选 API Key → ctx** |

---

## 9. 待讨论 / 已决

**已决**

- [x] 语言：**Python**
- [x] ctx：必填 `tenant` + `user_id`；`team_id` **可选**（无多组织则不传）
- [x] MCP：**A 单聚合**
- [x] 鉴权：Phase 0 **API Key → ctx**
- [x] 第一条垂直链：**销售单** `sale.create_order` → `sale.confirm_order`
- [x] Skill 分发：Phase 0 **仓库 `builtin|addon/*/skills/` 目录** + 接入说明（HTTP/zip 后置）
- [x] `needs_confirmation`：HMAC token，绑定 ctx + tool + args 摘要 + TTL；二次 call 带 `confirmation_token`

---

## 10. 一句话

> **先做能力层**：Python + 单聚合 MCP + API Key；垂直链为销售单 create→confirm；ctx 为 tenant + user_id（team_id 可选）；Chat 与编排后置。
