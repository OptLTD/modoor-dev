export type ChartLayout = { x: number; y: number; w: number; h: number }

export type ChartCard = {
  title: string
  type: 'table' | 'text' | 'count' | string
  /** 有值时按这些能力过滤；否则按 query.model 的 list 权限。 */
  access?: string[]
  layout: ChartLayout
  option?: {
    fields?: string[]
    content?: string
    count?: string
    method?: string
    prefix?: string
    suffix?: string
    note?: string
    help?: string
  }
  query?: {
    model?: string
    using?: string
    logic?: string
    limit?: number
    /** compare：点进去的这一侧，搜索合计 */
    label?: string
    sum?: string[]
    /** 写入所选财务期的字段，默认 basic.uterm */
    term?: string
    query?: Record<string, unknown>
  }
  /** compare 卡片的另一侧。type=query 搜索合计，type=report 报表 totals。期间由卡片切换写入。 */
  compare?: ChartValue
}

export type ChartValue = {
  type?: 'query' | 'report' | string
  label?: string
  model?: string
  using?: string
  /** query：从搜索 totals 相加的字段 */
  sum?: string[]
  /** query：写入所选财务期的字段，默认 basic.uterm */
  term?: string
  /** report：接口路径，如 /api/fleet/report/vehicle-pnl */
  path?: string
  /** report：totals 里的键 */
  total?: string
  query?: Record<string, unknown>
}

export type ChartsFile = Record<string, ChartCard[]>

export type ChartBoard = {
  id: string
  label: string
  brief?: string
}
