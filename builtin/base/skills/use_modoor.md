---
id: base.use_modoor
title: Use modoor system
summary: >
  Platform entry skill for modoor(木牍): users/roles/apps, wiki, documents,
  and where tenant custom skills are edited. Addon modules (fleet, …) keep
  their own skills.
when_to_use: |
  First skill for any modoor host session; or when the user asks about users,
  roles, apps, wiki pages, doc assets, or tenant skills (skill.query/read/write).
tools:
  - base.list_users
  - base.get_user
  - base.list_roles
  - base.get_role
  - base.list_apps
  - base.read_app
  - base.schema
  - base.search
  - wiki.query
  - wiki.read
  - wiki.write
  - doc.query
  - doc.read
  - doc.upload
  - skill.query
  - skill.read
  - skill.write
confirmations: []
---

# Skill: Use modoor system

Install this skill first, then connect MCP. Prefer tools listed here for
platform work. Domain addons (fleet, freight, …) publish **their own** skills —
follow those for business data.

## 先搞清概念再动手

遇到不熟悉的业务名词 / 流程 / 单据时，**先补理解，再查数或写操作**。优先级：

1. **Domain skill**（如 `fleet.assist_ops`）— 该业务模块怎么用、工具怎么调  
2. **Wiki** — 业务知识汇总与口径说明  
3. **Doc** — 原始材料、附件、制度全文  

Wiki 里常会链到 Doc；两边对照，不要凭空编概念。

## Base — 账号与权限

管租户里的**人、角色、已装应用**，回答「谁有什么权限 / 装了哪些模块」。

1. Users: `base.list_users(q=...)` / `base.get_user(username=...)`
2. Roles: `base.list_roles(q=...)` / `base.get_role(code=...)`
3. Apps: `base.list_apps` / `base.read_app(app_id="fleet")`

## Wiki — 业务知识库

存放**业务相关知识汇总**（项目下的页面树）：口径、流程说明、名词解释等。部分页面会引用或链到 Document 里的原文。

1. Projects: `wiki.query(resource="projects")`
2. Pages: `wiki.query(resource="pages", project_id=..., q=...)`
3. Read: `wiki.read(page_id=...)` — body 为 BlockNote JSON
4. Write（需非只读）: `wiki.write` — 更新传 `page_id`；新建传 `project_id`+`title`；`body` 可为 BlockNote JSON 或纯文本/markdown

## Doc — 文档库

存放**非结构化原文**（上传件、制度、合同扫描等），可检索与抽文本。Wiki 讲「怎么理解」，Doc 提供「原文依据」。

一份文件只属于一条记录的一个字段。来源在 `model`、`uukey`、`field` 上，`field` 存字段键。标签是人工分类，不是来源索引。

1. Search: `doc.query(q=..., tag=..., limit=...)` — `q` 匹配标题、文件名、标签、来源、备注和抽出的正文；`tag` 按一个标签精确筛选
2. Read: `doc.read(asset_id=..., full_text=true)` — 返回标签和来源。pending/running 则重试；失败勿编造
3. Upload（需非只读）: `doc.upload` — 文本用 `title`+`text`；二进制用 `filename`+`content_base64`。可带 `tags`，以及来源 `model`、`uukey`、`field`
4. 用 **asset id** 标识文档

## Skill 目录

租户自定义 / 覆盖的 SOP 在控制台 `/skill` 编辑，也可经 MCP：

1. List: `skill.query(q=..., module=..., source=...)`
2. Read: `skill.read(skill_id="freight.manage_shipments")` — 含 markdown 正文
3. Write（需非只读）: `skill.write` — 更新传 `skill_id`；新建传 `skill_key`+`title`（默认 `custom.*`）
4. **`base.*` 只读**，不可经 write 覆盖；模块文件 skill 改仓库 markdown，或用 write 写租户覆盖（非 base）

## Model — 业务数据契约

各业务模块用 **Model**（如 `fleet.vehicle`、`fleet.mileage`）描述实体字段、列表/表单视图与查询语义。PC 壳里的表格、透视页签都挂在这些 model 上；Agent **不直接改 schema**，通过该模块 skill 声明的 MCP tools 读写运行数据。

需要弄清「一张单有哪些字段 / 怎么筛 / 先汇总再下钻」时：跟 **`base.use_model`**（`base.schema` / `base.search` + domain aggregate·query·read）。

## MCP — 工具通道

**MCP = 宿主调用 modoor 的唯一执行面**（Streamable HTTP，通常 `{base}/mcp`）。Skill 教「怎么做」；MCP 提供「能调哪些 tool」。

1. 先装 Skill（本 skill + 相关 domain skill），再连 MCP。  
2. **只调用**当前任务 skill 里列出的 tools；不要扫全量 tool 列表瞎试。  
3. 鉴权：浏览器 OAuth，或 `Authorization: Bearer <agent_key>`。默认常为只读；写操作需非 readonly 令牌 / 明确授权。  
4. Prefer `query` / `read` / `aggregate`；mutate 仅在用户要求且权限允许时。

入口说明：`/agent/readme`（技能列表 + MCP 配置示例）。

## 禁忌

- Do not invent users, roles, apps, page ids, or document text.
- Call only MCP tools you are allowed to use; mutate only when the token is not read-only.
