# 期望（Expectations）

> 本文档只描述**我们要建成什么样的系统**。  
> **当前阶段优先级：先做 AI 能力层，暴露给其他 AI；不做自有 AI Chat / AI 编排。**  
> ctx：必填 `tenant` / `user_id`，可选 `team_id`。  
> Module 契约见 [`MODULE_CONTRACT.md`](./MODULE_CONTRACT.md)；本仓库计划见 [`AI_SYSTEM_PLAN.md`](./AI_SYSTEM_PLAN.md)。

---

## 0. 阶段策略（先读这个）

| 阶段 | 做什么 | 不做什么 |
|---|---|---|
| **现在（Capability Layer）** | Module 整合 + **Skill / MCP 发布** + ACL / 审计 / 确认语义 + **ui-web** | 自研 Chat UI、Planner、多 Agent 编排、**ui-app** |
| **以后（可选）** | 自有 Agent Runtime / Chat + Canvas / **ui-app** | — |

定位一句话：

> 本系统先是 **给其他 AI 用的业务能力层**（Skill + MCP），不是又一个 Chatbot。  
> 谁来对话、谁来编排，由**外部 AI / 宿主产品**决定；我们保证能力可发现、可调用、可鉴权、可审计。

```text
┌─────────────────────────────────────────────┐
│  外部 AI（Cursor / Claude / 自建 Agent / …）  │  ← 编排与对话在外面
└──────────────────────┬──────────────────────┘
                       │ Skill 发现 + MCP call
                       ▼
┌─────────────────────────────────────────────┐
│  本项目 = AI 能力层（Capability Layer）        │  ← 我们先做这个
│  Registry · MCP · Skill Catalog · ACL · Audit │
└──────────────────────┬──────────────────────┘
                       ▼
                 各业务 Module
```

---

## 1. 产品期望（能力层）

长期仍可走向 AI-first 的「可插拔业务平台」，但**第一里程碑只交付能力层**：

| 期望 | 说明 |
|---|---|
| 对外形态 | 稳定发布 **MCP**（能调什么）+ **Skill**（怎么做事） |
| 消费者 | **其他 AI / Agent Runtime / 自动化宿主**，不是终端用户 Chat |
| 业务扩展 | 以 **Module** 为扩展单位（可安装、可依赖、可版本） |
| 账本边界 | 外部 AI 只经 MCP 落库；服务端强制 ACL 与审计 |
| 能力暴露 | 契约与元能力可发现；L2 实现不裸奔 |
| 确认语义 | 高风险 Tool 返回 `needs_confirmation`（由**调用方 AI/宿主**完成人机确认） |

一句话：

> **我们卖的是可插拔业务能力（Module → Skill/MCP）；Chat 与编排是别人的事（或我们的下一阶段）。**

---

## 2. 对外能力面：Skill + MCP

| 概念 | 期望含义 | 本阶段不负责 |
|---|---|---|
| **MCP** | 以 **Tools** 为主；Resources 可由能力层派生；Prompts 非必须（SOP 用 Skill） | 对话、规划、选模型 |
| **Skill** | 领域 SOP：何时用哪些 tool、步骤、禁忌、确认点 | 自动执行 Skill 的编排引擎 |
| **Module** | 打包并产出 Skill + MCP 素材 | 直接对接终端用户 UI |

### 2.1 对 MCP 的期望

- 外部 AI 只通过 MCP 发现与调用（list / call）
- 调用携带 **ctx**：必填 `tenant`、`user_id`；可选 `team_id`（无多组织则不传）；服务端强制 ACL
- Tool：稳定名、input/output schema、错误码（**模块必提供**）
- Resource / Prompt：非模块必导出；需要时由能力层派生或不实现
- 高风险：返回 `needs_confirmation` + 结构化 payload；由调用方处理确认后再提交

### 2.2 对 Skill 的期望

- 以可分发文档/清单形式提供（供外部 AI 加载进上下文或 Skill 系统）
- 只引用已 export 的 MCP tools
- 可按 module / 领域检索，避免一次塞全部
- 手写与 AI 生成同构、可版本

### 2.3 对「造 Module」的期望（可稍后）

- L0 Meta 仍以 MCP Tools 暴露，供**外部**「模块设计师」AI 调用
- 生成物必须是正式 Module，经安装进入 Registry
- 当前阶段可先手写 Module，Meta 生成放后续

### 2.4 给外部 AI 的接入期望

- 一份清晰的 **连接说明**（MCP endpoint / auth / 如何加载 Skill）
- 可用任意兼容 MCP 的宿主验证（如 Cursor、Claude Desktop、自建 client）
- 幂等、错误码、确认流有文档，方便第三方编排

---

## 3. 能力分层（L0 / L1 / L2）

| 层 | 期望 | 外部 AI 默认可见 |
|---|---|---|
| **L0 Meta** | 造 Module 的元能力 | 仅强权限调用方 |
| **L1 Public** | Module 显式 export 的 Tool / Resource / Skill | 按 ACL |
| **L2 Private** | 内部实现 | 否 |

原则：发现 ≠ 调用；最小暴露；未列入 `exports.*` 不得进 MCP/Skill。

---

## 4. 后续期望（明确后置，不阻塞能力层）

以下写进路线图，**不是当前交付范围**：

### 4.1 自有 AI Chat / 编排（后置）

- 自研对话 UI、Planner、多步 Agent、会话记忆
- 本层已提供的 Skill/MCP 应可被自有 Runtime **零改契约**复用

### 4.2 UI：`ui-web`（已开始）与 `ui-app`（后置）

| 字段 | 阶段 | 说明 |
|---|---|---|
| **`ui-web`** | 现在 | 模块 `app`（`resolve_entry`）/ `external`；登录为平台 template；见 MODULE_CONTRACT §2.1 |
| **`ui-app`** | **以后** | 原生 / 移动 App 壳、设备桥（扫码/GPS）、离线与推送等 |

对 **`ui-app`** 的期望（本阶段**不实现**）：

- Module 可在 `module.yaml` 预留 `ui-app`（入口、能力声明、`mobile_hints` 等），契约可先写
- App 壳仍须经同一 MCP / Ability 调用业务；**禁止** App 专用写库旁路
- Chat + Canvas、PWA/原生安装、设备输入属此轨
- 与 `ui-web` 共用 Module 的 tools/skills/ability，不另起一套业务 API

### 4.3 人机确认宿主（后置或由调用方提供）

- 能力层只定义确认协议；弹窗/推送/审批页由外部 AI 宿主或未来 Shell 实现

---

## 5. 非目标（当前阶段）

- 自研 AI Chat、AI 编排、多 Agent 框架
- 复刻完整传统 ERP 菜单 / 应用树
- 终端用户 Mobile App（可作为更后期）
- Agent 直连 DB 或旁路 MCP
- 无 Module 产物的影子改表

---

## 6. 成功标准（能力层验收）

- [ ] 外部 AI 仅通过 **MCP** 可完成一条垂直业务链（如创建销售单）
- [ ] 配套 **Skill** 可被外部宿主加载，并正确指引 tool 使用
- [ ] 新装 Module 后，exports 自动出现在 MCP list / Skill catalog（受 ACL）
- [ ] 高风险 Tool 返回标准 `needs_confirmation`；确认后可安全提交并留审计
- [ ] 提供最小接入文档；至少一种外部 MCP 客户端联调通过
- [ ] （可选）L0 Meta 尚未具备时，手写 Module 路径完整即可

---

## 7. 文档关系

```text
EXPECTATIONS.md          ← 期望：先能力层，后 Chat/编排/Mobile Shell
        ↓ 约束
MODULE_CONTRACT.md       ← Module 如何产出 Skill + MCP
        ↓ 实现
AI_SYSTEM_PLAN.md        ← 本项目：整合并对外暴露能力层
```
