# 版本管理（Core）

本仓（modoor-dev）的 **Core** 按 **同一 semver** 演进：后端运行时与共享前端是一套版本，不是两套。

当前版本号以根目录 [`pyproject.toml`](../pyproject.toml) 的 `version` 为准（例如 `0.1.0`）。

## Core 包含什么

| 路径 | 角色 |
|------|------|
| `modoor/` | 引擎、运行时、Web/MCP、loader |
| `builtin/` | 平台模块（base / doc / wiki / skill / flow …） |
| `shared/` | 共享前端（`@modoor/hooks` / `widget` / `views`） |
| `addon/sale`（demo） | 随 Core 发布的示例业务；**不**代表全部业务能力 |

以下 **不属于** Core 版本，由外部 addon 树自行版本化，但须声明兼容的 Core 范围：

- 通过 `MODOOR_ADDON_ROOT` 挂载的外部 `addon/*`（如私有业务仓）

## Semver 规则

格式：`MAJOR.MINOR.PATCH`（[SemVer 2.0](https://semver.org/)）。

在 `0.x` 阶段：`MINOR` 可含不兼容变更，但仍应在发布说明中标明；进入 `1.0.0` 后严格按下表。

| 变更类型 | 版本位 | 典型例子 |
|----------|--------|----------|
| **Breaking** | **MAJOR** | 删除/改名稳定 HTTP/MCP API；`module.yaml` / Record 契约不兼容；`shared` 导出路径或 props 不兼容；loader 发现约定变更导致旧模块无法加载 |
| 功能、向后兼容 | MINOR | 新 API、新 builtin、`exports.jobs` 新字段（旧模块可忽略）、shared 新增组件且旧用法仍可用 |
| 修复、文档、内部重构（对外行为不变） | PATCH | bugfix、性能、注释 |

**前后端同版本**：发布 Core `X.Y.Z` 时，`modoor` 包、`shared` 与随仓 demo 一并按该号理解；不要出现「后端 0.3、hooks 0.5」两套对外版本。  
（`shared/*/package.json` 内部可暂留 `0.1.0`，以仓库/`pyproject.toml` 为准；后续可与 Core 对齐。）

## 什么算 Breaking（契约面）

优先看这些对外面（细则见 [`MODULE_CONTRACT.md`](./MODULE_CONTRACT.md)、[`SCHEMA_CONTRACT.md`](./SCHEMA_CONTRACT.md)）：

1. **HTTP / MCP**：路径、必填字段、错误码语义、鉴权方式  
2. **Module 约定**：`module.yaml` 必填项、`exports.*`、jobs 调度字段、loader 文件约定（`jobs.py` / `adapters.py` / `webui.py` …）  
3. **Record / 模型引擎**：schema 形状、查询语义、adapter 职责边界  
4. **shared UI**：`@modoor/*` 的 public export、组件 props / 事件；删除或改名即 MAJOR  
5. **挂载语义**：`MODOOR_ADDON_ROOT`、Python `import addon.*` 前缀约定  

模块**内部**表结构变更走该模块自己的 `migrate` + 模块 `version`；若迫使所有外部模块改代码才能跑，仍算 Core Breaking。

## 外部 addon 树如何声明兼容

外部业务仓（私有 pro 等）应在 README 或 `pyproject.toml` 中写明：

```text
Requires Core (modoor): >=0.1.0,<0.2.0
```

约定：

- 只保证在声明区间内与 Core 联调通过  
- Core **MAJOR** 升级后，业务仓应跟进并 bump 自己的兼容声明  
- 本地开发：兄弟目录 + `MODOOR_ADDON_ROOT`；`shared` 通常由业务仓软链到本仓 `shared/`

业务仓**不要**复制一份 `shared` 长期分叉；以本仓 `shared` 为准。

## 发布检查清单（Core）

发版前：

- [ ] 更新 `pyproject.toml` `version`  
- [ ] Changelog / 发布说明区分 Breaking / 兼容新增 / 修复  
- [ ] Breaking：列出迁移步骤（外部模块 / 前端改什么）  
- [ ] 冒烟：无外挂 addon 时 `builtin` + `sale` demo 可起；有外挂时抽测 1～2 个业务模块  
- [ ] 若改了 `shared` public API，按 MAJOR 或明确「仅 0.x 兼容窗口」  

## 与模块 `module.yaml` version 的关系

- **Core version**：整仓平台契约（本文）  
- **模块 `version`**：单个 builtin/addon 模块自身演进（见 MODULE_CONTRACT）  

模块 minor/patch 可独立涨；一旦模块变更依赖 **Core Breaking**，必须先升 Core，再升模块，并更新外部仓的「Requires Core」区间。

## 一句话

**Core = 后端 + builtin + shared，同一 semver；破坏契约就升大版本；外部 addon 声明自己兼容的 Core 范围。**
