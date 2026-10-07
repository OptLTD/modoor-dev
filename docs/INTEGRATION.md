# 外部接入（Phase 0）

## MCP

- **形态**：单聚合 Server（A）
- **传输**：stdio（Cursor / Claude Desktop 本地进程）
- **进程入口**：`modoor-mcp` 或 `python -m modoor`

### Tools

| 名称 | risk | 说明 |
|---|---|---|
| `sale.create_order` | medium | 创建草稿销售单 |
| `sale.get_order` | low | 按 id 查询 |
| `sale.confirm_order` | high | 首次返回 `needs_confirmation`；带 token 二次提交 |
| `wiki.create_project` | medium | 创建 wiki 项目（含首页） |
| `wiki.list_projects` | low | 列出项目 |
| `wiki.create_page` | medium | 在项目下创建页面（可选 parent_id；body 为 BlockNote JSON） |
| `wiki.update_page` | medium | 按 page_id 更新 title/body |
| `wiki.get_page` | low | 按 page_id 读取 |
| `wiki.list_pages` | low | 列表/检索（不含正文） |
| `wiki.delete_page` | high | 删除；需 confirmation_token（不可删首页） |
| `catalog.list_skills` | low | 列出 Skill |

### Resources

- `skill://sale/create_and_confirm_order` — 销售 Skill
- `skill://wiki/manage_page` — Wiki Skill

## 鉴权

环境变量注入（MCP 宿主 `env`）：

- `MODOOR_API_KEY` — 必须与服务器期望一致
- `MODOOR_TENANT` / `MODOOR_USER_ID` / 可选 `MODOOR_TEAM_ID`
- `MODOOR_CONFIRM_SECRET` — confirmation HMAC
- `DATABASE_URL`

调用结果统一 JSON 字符串：`status=ok|error|needs_confirmation`。

## 确认流

1. `sale.confirm_order(order_id=...)` → `needs_confirmation` + `confirmation_token`
2. 宿主/人确认后：`sale.confirm_order(order_id=..., confirmation_token=...)`（args 须一致）
3. Token 绑定 ctx + tool + args 哈希 + TTL（默认 600s）

## Skill 加载

- 仓库路径：`addon/sale/skills/create_and_confirm_order.md`
- 或 MCP resource / `catalog.list_skills`
