import type { SchemaField } from './record'
import type { ReferDict } from './fieldMeta'

/** 表格 / sheet 视图的 schema 描述 */
export type SchemaTable = {
  model: string
  using?: string
  title?: string
  fields: SchemaField[]
  /** 原始字段定义；筛选用 origin[key] 映射类型 */
  origin?: Record<string, SchemaField>
  sticky?: string[]
  refers?: ReferDict
  clicks?: { uukey: string; label?: string; action?: string; group?: string; seqno?: number }[]
  /** 工具栏快捷筛选字段 key */
  filters?: string[]
  createDefaults?: Record<string, unknown>
  request?: SchemaRequest
}

/** 列表 / sheet 请求参数 */
export type SchemaRequest = {
  page?: number
  size?: number
  query?: Record<string, unknown>
  order?: { field: string; order: string }
}
