# Modoor — AI Capability Layer (Phase 0)

以可安装 **Module** 为扩展单位的 AI 能力层：对外发布 **Skill + MCP**，供外部 AI 调用。

当前能力：`base`（app/user/role）、`sale` demo（create→confirm）、`wiki`（页面 CRUD）；鉴权为 API Key → ctx。  
外部应用 demo：`external/board`、`external/pulse`（经 Modoor 注册中心发现）。

整合层包结构：

```text
builtin/    # 平台模块：base / doc / wiki / skill / flow
addon/       # 业务 demo：sale（完整可运行）
shared/       # 共享前端：hooks / widget / views
external/     # 外进程 demo（board / pulse）
modoor/
  core/       # settings / ctx / db / errors / security
  runtime/    # auth / audit / confirmation / tool runner / MCP / worker
  platform/   # module 启停 / loader / 外部服务注册 / bootstrap
  web/        # PC Shell
```

本仓是完整可运行方案（含 sale demo）。需要其它业务模块时，通过 `MODOOR_ADDON_ROOT` 指向外部 `addon/` 目录即可（发现与 `import addon.*` 都会走该路径）。

设计文档见 [`docs/`](./docs/)，实现约定见 [`docs/PHASE0.md`](./docs/PHASE0.md)。

## 快速开始

```bash
cd /path/to/modoor-dev
cp .env.example .env     # DATABASE_URL 指向已有 Postgres
make setup
make dev base            # 建表 + 初始化 + 启动 Web：http://127.0.0.1:8765
# 默认账号 admin / admin123
# make mcp               # MCP（stdio）
# make test
```

### 外挂 addon（可选）

```bash
# .env
MODOOR_ADDON_ROOT=/path/to/external/addon
```

等价手工步骤：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 冒烟：直接跑销售链（不经 MCP 宿主）
python addon/sale/tests/smoke_sale_flow.py

# 启动 MCP（stdio，供 Cursor 等连接）
modoor-mcp
# 或: python -m modoor
```

本地只用 PostgreSQL：把 `DATABASE_URL` 指到已有实例（本仓不自带数据库进程）。没有 Postgres 时才用 `make db`。测试走独立库 `modoor_test`，不会清空开发库。

## Cursor 接入

在 MCP 配置中增加（路径改成你的仓库绝对路径）：

```json
{
  "mcpServers": {
    "modoor": {
      "command": "/path/to/modoor-app/.venv/bin/modoor-mcp",
      "env": {
        "MODOOR_API_KEY": "dev-key-change-me",
        "MODOOR_TENANT": "demo",
        "MODOOR_USER_ID": "user-1",
        "MODOOR_CONFIRM_SECRET": "dev-confirm-secret-change-me",
        "DATABASE_URL": "postgresql+psycopg://modoor:modoor@127.0.0.1:5432/modoor"
      }
    }
  }
}
```

Skill 文档路径：`addon/sale/skills/create_and_confirm_order.md`  
也可经 MCP resource：`skill://sale/create_and_confirm_order`，或 tool `catalog.list_skills`。

更细说明见 [`docs/INTEGRATION.md`](./docs/INTEGRATION.md)。

## ctx

| 字段 | 必填 | 来源（Phase 0） |
|---|---|---|
| `tenant` | 是 | `MODOOR_TENANT` |
| `user_id` | 是 | `MODOOR_USER_ID` |
| `team_id` | 否 | `MODOOR_TEAM_ID` |

进程启动时校验 `MODOOR_API_KEY`；当前一进程绑定一套 ctx。
