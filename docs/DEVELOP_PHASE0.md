# Phase 0 实现约定

> 与 [`AI_SYSTEM_PLAN.md`](./AI_SYSTEM_PLAN.md) 已决项对齐；指导本仓第一版代码。

## 目标

外部 AI（如 Cursor）经 **单聚合 MCP + API Key**，完成：

`sale.create_order` →（确认）→ `sale.confirm_order`，数据落入自有库。

## 栈

| 项 | 选择 |
|---|---|
| 语言 | Python 3.11+ |
| MCP | FastMCP / `mcp` SDK，stdio（Cursor 本地） |
| ORM | SQLAlchemy 2.x |
| DB | PostgreSQL（`DATABASE_URL` 指向已有实例） |
| 鉴权 | 环境变量 API Key → ctx |

## ctx

```json
{ "tenant": "demo", "user_id": "u1", "team_id": null }
```

- `tenant` / `user_id` 必填；`team_id` 可选。
- Tool 只读 ctx，不解析凭证。

## API Key

环境变量（启动 MCP 进程时注入）：

| 变量 | 含义 |
|---|---|
| `MODOOR_API_KEY` | 调用方持有的 key（与服务器配置一致才启动/接受调用） |
| `MODOOR_TENANT` | 映射到 ctx.tenant |
| `MODOOR_USER_ID` | 映射到 ctx.user_id |
| `MODOOR_TEAM_ID` | 可选 |
| `MODOOR_CONFIRM_SECRET` | 签发 confirmation token 的 HMAC 密钥 |

Phase 0：一个进程绑定一套 ctx（由上述 env 决定）。多租户多 key 表放到 Phase 1。

## needs_confirmation

1. 高风险 tool（`sale.confirm_order`）首次调用：校验权限后**不落确认**，返回：

```json
{
  "status": "needs_confirmation",
  "confirmation_token": "<hmac>",
  "expires_at": "<iso8601>",
  "tool": "sale.confirm_order",
  "summary": { "...": "给人看的摘要" },
  "args": { "...": "将要执行的参数" }
}
```

2. 调用方（人或宿主）确认后，**用相同 args** 再 call，并多传 `confirmation_token`。
3. Token 校验：HMAC(`tenant|user_id|team_id|tool|canonical_args|exp`)，且未过期；ctx 必须与签发时一致。
4. TTL 默认 10 分钟。

## Skill

- 路径：`addon/sale/skills/*.md`
- Phase 0 不强制 HTTP；接入说明里写清「把该目录加入 Agent Skill / 上下文」。
- MCP 可提供只读 resource：`skill://sale/...` 便于宿主拉取。

## 工具面（最小）

| Tool | risk | 说明 |
|---|---|---|
| `sale.create_order` | medium | 创建草稿单 |
| `sale.confirm_order` | high | 需 confirmation_token |
| `sale.get_order` | low | 只读，便于验收 |

Phase 0 客户/产品用字符串字段即可（`partner` / 行上的 `product_name`），不强制先装 partner/product 模块。
