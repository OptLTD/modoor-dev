---
id: base.use_model
title: Use modoor models
summary: >
  How business Models work with schema views and Agent verbs —
  overview via aggregate/digest first, then query drill-down; plus
  base.schema / base.search and full query operators.
when_to_use: |
  Need to understand a module's data shape, list vs detail vs rollup,
  table/digest views (using), filters, or how MCP tools relate to Models.
tools:
  - base.schema
  - base.search
confirmations: []
---

# Skill: Use modoor models

业务数据挂在 **Model** 上（如 `fleet.vehicle`、`fleet.mileage`）。PC 壳表格/透视、
engine、领域 MCP tools 共用同一套契约。具体 resource / metric 名以各 **domain skill**
（如 `fleet.assist_ops`）为准。

## 感知顺序（先总后细）

对**业务全局 / 一段时间概况**，先汇总再下钻，避免一上来拉全量明细：

1. **概况** — 领域 `<module>.aggregate`，或已有 **digest `using`** + `base.search`（与用户看板同口径）  
2. **下钻明细** — 再 `<module>.query` 拉列表  
3. **单条** — `<module>.read`

不要用 query 硬扫全表来「感受业务」；也不要用 aggregate 代替用户要的逐条明细。

## 概念

| 概念 | 含义 |
|---|---|
| **Model** | 业务实体：`\<module\>.\<name\>`，字段多为 `basic.*` / 嵌套组键 |
| **using** | 视图名：`default` / `table` / `pivot-*` / `rpt.*` … 决定列、默认筛、是否聚合 |
| **Schema** | `model`+`using` 下的 fields / filters / query / digest 元数据 |
| **Query** | 筛选 map：键为 `field` 或 `field:OP` |
| **Digest** | `tables.json` 里配置了 `extra.group` + `extra.count` 的视图（可再 `append` / `pivot`） |

Agent **不直接改 schema / 不猜表结构**。

## Schema

默认：

```
base.schema(model="fleet.mileage")
```

（`using=default`）。要对齐某张用户看板时再传同名 `using`：

```
base.schema(model="fleet.freight", using="rpt.site.loadRate")
```

看返回里的 fields、filters、默认 query，以及 digest 时的 `others.$digest` / `extra.group|count|append`。  
`kind="input"` 仅在对表单可写字段时使用。

## 筛选算子（engine query）

键写法：`"field"`（默认 EQ）或 `"field:OP"`；也可用嵌套 `{ "field": { "IN": [...] } }`。

| OP | 含义 | 值 |
|---|---|---|
| `EQ` | 等于（可省略） | 标量 |
| `NE` | 不等于 | 标量 |
| `IN` | 属于集合 | **数组** |
| `LIKE` | 包含（不区分大小写；SQL 两侧加 `%`） | 字符串片段，**不要**自写 `%` |
| `GT` / `GTE`（或 `GE`） | 大于 / 大于等于 | 日期或可比较标量 |
| `LT` / `LTE`（或 `LE`） | 小于 / 小于等于 | 同上 |
| `BTW` | **闭区间** | **长度为 2 的数组** `[from, to]` |
| `NIL` | 空 / 非空 | 真值（`true`/`1`）表示「为空」；假表示「非空」 |
| `NNL` | 非空 | （有值即可；常与 EQ 空串互补） |
| `RCT` | 相对过去区间 → 展开为 BTW | 见下表 token |
| `FTR` | 相对未来区间 → 展开为 BTW | 见下表 token（与 RCT 共用展开器） |

### BTW 正确用法

```
"basic.utime:BTW": ["2026-09-01", "2026-09-30"]
```

- 必须是 **二元数组**；单端请用 `GTE` / `LTE`。  
- 日期按 **日历日闭区间**（含起止日）；优先 `YYYY-MM-DD`。  
- 不要写成 `"2026-09-01~2026-09-30"` 字符串。

### RCT / FTR 可用 token

展开为本地日历的 `[start, end]`（含今天相关边界）。**未知 token 会落到近 30 天**，勿随意发明。

**日历块（RCT）：**

| Token | 含义 |
|---|---|
| `CURRENT_WEEK` | 本周（周一～周日） |
| `PREVIOUS_WEEK` | 上周 |
| `CURRENT_MONTH` | 本月 |
| `PREVIOUS_MONTH` | 上月 |
| `CURRENT_YEAR` | 本年 |
| `PREVIOUS_YEAR` | 去年 |
| `CURRENT_TERM` | 本期（财务期间；默认 timeTerm 切日 **26**） |
| `PREVIOUS_TERM` | 上期 |

本期/上期按「每月 `start` 日切到下一期间」展开为 **日期闭区间**（挂在 `basic.utime` 等日期字段上）。例：切日 26 时，9 月 10 日的本期 = `2026-08-26`～`2026-09-25`。用于 `basic.uterm`（YYYYMM 整数）时请改 EQ/IN，不要用 TERM 的日期 BTW。

**近一段（RCT，从今天往回）：**

| Token | 含义 |
|---|---|
| `RECENT_3_DAYS` | 近 3 天～今天 |
| `RECENT_1_WEEK` | 近 7 天 |
| `RECENT_2_WEEK` | 近 14 天 |
| `RECENT_1_MONTH` | 近 1 个日历月～今天 |
| `RECENT_2_MONTH` | 近 2 月 |
| `RECENT_3_MONTH` | 近 3 月 |
| `RECENT_6_MONTH` | 近 6 月 |

**未来一段（FTR，从今天往前）：**

| Token | 含义 |
|---|---|
| `FUTURE_1_WEEK` / `FUTURE_2_WEEK` | 今天～+7 / +14 天 |
| `FUTURE_1_MONTH` … `FUTURE_6_MONTH` | 今天～+N 日历月 |

示例：

```
"basic.utime:RCT": "CURRENT_MONTH"
"basic.utime:RCT": "RECENT_3_MONTH"
"basic.expired_at:FTR": "FUTURE_1_MONTH"
"basic.status": "idle"
"basic.plate:LIKE": "沪A"
"basic.dest:IN": ["上海", "苏州"]
```

领域 `*.query` 的扁平参数会由工具映射成上述 query；以 tool docstring 为准。

## Query — 明细列表

`<module>.query`：下钻明细。`resource` 多为单数实体名。  
列表 MCP 一般 `using=default`，避免误用 `table` 上的「仅本月」默认筛。

## Read — 单条

`<module>.read`：一条详情（可含领域补全）。不要对 read 塞列表筛选项。

## Aggregate / Digest — 汇总与用户看板

两条路，都先于明细 query：

### A. 领域 aggregate

`<module>.aggregate(metric=...)`：模块定制汇总 / 核算（如 `vehicle_pnl`）。`metric` / `group_by` / `uterm` 见 domain skill。

### B. 已有 digest `using`（与 PC 同界面）

模块 `tables.json` 里带 `extra.group` + `extra.count` 的视图，即用户看到的透视/报表页签。

1. 用 `base.schema(model, using="<digest>")` 确认列与默认筛。  
2. 用 **同一 `using`** 取数：

```
base.search(model="fleet.freight", using="rpt.site.loadRate")
base.search(
  model="fleet.mileage",
  using="pivot-driver",
  query={"basic.utime:RCT": "RECENT_3_MONTH"},
  page=1,
  size=50,
)
```

`query` **合并覆盖**视图默认 query（可收窄时间/车牌等）。返回 `values` / `count` / `totals` 与 PC 表同源。

### Digest 配置语法（读懂 schema / 仓库）

写在 `tables.json` → `extra`（Agent **不要现场发明**新视图；用已有 `using`）：

**group** — `index|sort[|format]`

| 段 | 含义 |
|---|---|
| `index` | 分组字段，如 `basic.dest` |
| `sort` | `ASC` / `DESC` |
| `format` | 可选：`date` / `month`（时间桶） |

例：`"basic.dest|ASC"`、`"basic.utime|ASC|month"`

**count** — `index|func[|label]`

| func | 含义 |
|---|---|
| `CNT` | 行数（`index` 常用 `basic.uukey`） |
| `UNQ` | 去重计数 |
| `SUM` / `AVG` / `MAX` / `MIN` | 聚合 |

例：`"goods.volume|SUM|配送升数"`、`"basic.utime|UNQ|出车天数"`

**append** — 合成列 `field|label[|ftype|formula]`

- 结果键一般为 `append.{field}`  
- `ftype` 默认 `NUMERIC`  
- formula 可用 count 列的 **label 或字段名**；`total(某列)` = 全表合计行上的值（占比类）

例：

```
"loadRate|满载率(%)|NUMERIC|配送升数*100/满载升数"
"volumeRate|运量占比(%)|NUMERIC|配送升数*100/total(配送升数)"
```

**pivot**（可选）— `pivotField|valueField|on`：把某维展开为列（如月度看板）。

完整示例（站点满载率视图片段）：

```json
"extra": {
  "group": ["basic.dest|ASC"],
  "count": [
    "basic.uukey|CNT|排班趟数",
    "goods.volume|SUM|配送升数",
    "goods.capacity|SUM|满载升数",
    "goods.freight|SUM|运费收入"
  ],
  "append": [
    "loadRate|满载率(%)|NUMERIC|配送升数*100/满载升数",
    "volumeRate|运量占比(%)|NUMERIC|配送升数*100/total(配送升数)"
  ]
}
```

对应取数：`base.search(model="fleet.freight", using="rpt.site.loadRate")`。

## 与 PC / MCP

```
PC SchemaView(using=…)
        │
        ▼
  engine
        ├── base.schema(model, using)     → 契约 / digest 定义
        ├── base.search(model, using, …)  → 与 UI 同口径的 values
        └── Domain MCP
              aggregate → 概况 / 核算
              query     → 下钻明细
              read      → 单条
```

## 推荐步骤

1. `base.use_modoor` + 本 skill + **domain skill**。  
2. 概念不清 → Wiki / Doc；字段不清 → `base.schema`。  
3. **先** aggregate 或 digest `base.search` 看概况 → **再** query 下钻 → 必要时 read。  
4. 只调用已声明 tools；无数据不编造。

## 禁忌

- 不要直接改库、猜表名或绕过 MCP。  
- 不要一上来 query 全量明细「摸底」。  
- 不要把 `table` 默认时间筛当成全量历史。  
- 不要臆造 RCT token 或 BTW 单值；不要臆造未导出的 digest `using`。
