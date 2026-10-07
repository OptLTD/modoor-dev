export type ChartLayout = { x: number; y: number; w: number; h: number }

export type ChartCard = {
  title: string
  type: 'table' | 'text' | 'count' | string
  layout: ChartLayout
  option?: {
    fields?: string[]
    content?: string
    count?: string
    method?: string
    prefix?: string
    suffix?: string
  }
  query?: {
    model?: string
    using?: string
    logic?: string
    limit?: number
    query?: Record<string, unknown>
  }
}

export type ChartsFile = Record<string, ChartCard[]>

export type ChartBoard = {
  id: string
  label: string
  brief?: string
}
