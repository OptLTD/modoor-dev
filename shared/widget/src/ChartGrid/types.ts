export type ChartGridTab = { id: string; label: string }

export type ChartGridColumn = { key: string; label: string }

export type ChartGridRow = { key: string; uukey?: string; cells: string[] }

/** 一张已经排好位置、填好展示数据的卡片。 */
export type ChartGridCard = {
  key: string
  title: string
  type: string
  style: Record<string, string>
  loading?: boolean
  error?: string
  total?: number | null
  prefix?: string
  suffix?: string
  clickable?: boolean
  content?: string
  columns?: ChartGridColumn[]
  rows?: ChartGridRow[]
}
