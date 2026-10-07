import { post } from './http'

export type SchemaGroup = {
  uukey: string
  title?: string
  gtype?: string
  seqno?: number
  model?: string
  extra?: Record<string, unknown>
}

export type SchemaField = {
  uukey: string
  field: string
  label: string
  /** 表头悬停说明 */
  remark?: string
  ftype: string
  group: string
  /** 分组标题，列设置里用来区分同名标签 */
  gname?: string
  seqno?: number
  index?: string
  width?: number
  shown?: boolean
  refer?: { using?: string; keyby?: string; txtby?: string }
  options?: { label?: string; value?: string; uukey?: string }[]
  extra?: Record<string, unknown>
}

export type SchemaClick = {
  uukey: string
  label?: string
  action?: string
  ctype?: string
  seqno?: number
  group?: string
  /** Create-menu item: which input view to open, e.g. general / engineering. */
  using?: string
  extra?: { using?: string }
}

export type SchemaTable = {
  model: string
  using?: string
  title?: string
  sticky?: string[]
  fields: SchemaField[]
  /**
   * 原始字段定义（按 uukey）。digest 等场景会改写 fields[].ftype；
   * 快捷筛选 / FilterPanel 优先用 origin[key] 映射交互类型。
   */
  origin?: Record<string, SchemaField>
  clicks?: SchemaClick[]
  /** 工具栏快捷筛选字段 key，如 basic.status */
  filters?: string[]
  refers?: Record<string, unknown>
  /** tables.json extra 原样透传 */
  others?: Record<string, unknown>
  /** 批量能力：update=批量修改，insert=批量新增（来自 extra.sheet） */
  sheet?: string[]
  /** 新建表单预填（与 RecordDialog create + row 配合） */
  createDefaults?: Record<string, unknown>
  request?: {
    page?: number
    size?: number
    query?: Record<string, unknown>
    order?: { field: string; order: string }
  }
}

export type SearchFacet = {
  overflow?: boolean
  options?: { value: string; label: string }[]
}

export type SearchResult = {
  page?: number
  size?: number
  values?: Record<string, unknown>[]
  count?: number
  refers?: Record<string, unknown>
  totals?: Record<string, unknown> | null
  /** 表头筛选：字段 unique；overflow 时前端回退原 UI */
  facets?: Record<string, SearchFacet> | null
}

export async function fetchSchema(model: string, using = 'default', scene = 'SEARCH') {
  return post<{
    model: string
    using: string
    scene: string
    table: SchemaTable
    tabs?: { using: string; label: string }[]
    source?: {
      fields?: Record<string, SchemaField>
    }
  }>('/api/record/schema', { model, using, scene, page: 1, size: 50 })
}

export async function searchRecords(
  model: string,
  using = 'default',
  page = 1,
  size = 50,
  opts: { query?: Record<string, unknown>; order?: { field: string; order: string } } = {},
) {
  return post<SearchResult>('/api/record/search', {
    model,
    using,
    scene: 'SEARCH',
    page,
    size,
    query: opts.query,
    order: opts.order,
  })
}

export type RecordOplogItem = {
  id: string
  model?: string | null
  code?: string
  utime?: string | null
  created_at?: string | null
  action?: string | null
  values?: {
    model?: string
    actor?: number | string
    team_id?: number
    diff?: Record<string, { old?: unknown; new?: unknown }>
    [key: string]: unknown
  }
}

/** Modification history for one record (base.oplog by business code). */
export async function fetchRecordOplogs(
  model: string,
  uukey: string,
  opts: { limit?: number } = {},
) {
  return post<{ items: RecordOplogItem[]; count: number }>('/api/record/oplogs', {
    model,
    uukey,
    limit: opts.limit ?? 200,
  })
}

export type RecordEntityHead = {
  title?: string
  subtitle?: string
  badge?: string
  fields?: string[]
}

export type RecordEntityTab = {
  id: string
  label: string
  kind: 'fields' | 'relation'
  /** 字段 key 列表；可用 `---` 或 `|` 插入分割线 */
  fields?: string[]
  model?: string
  using?: string
  /** related row field to filter, e.g. basic.company */
  queryKey?: string
  /** current entity field providing the filter value, e.g. basic.uukey */
  queryFrom?: string
  query?: Record<string, unknown>
}

export type RecordEntityAction = {
  id: string
  label: string
  action?: string
  variant?: 'primary' | 'danger' | 'ghost'
  disabled?: boolean
  hint?: string
}

/** Props/config for RecordEntity component (frontend only). */
export type RecordEntityConfig = {
  head?: RecordEntityHead
  tabs?: RecordEntityTab[]
  actions?: RecordEntityAction[]
}

export async function fetchInputSchema(
  model: string,
  using = 'default',
  scene = 'DETAIL',
  uukey?: string,
) {
  return post<{
    model?: string
    using?: string
    scene?: string
    input: {
      title?: string
      fields?: SchemaField[]
      groups?: SchemaGroup[]
      values?: Record<string, unknown>
      refers?: Record<string, unknown>
    }
  }>('/api/record/input', { model, using, scene, ...(uukey ? { uukey } : {}) })
}

export async function upsertRecords(
  model: string,
  batch: Record<string, unknown>[],
  using = 'default',
) {
  return post<{ records: unknown[] }>('/api/record/upsert', {
    model,
    using,
    scene: 'UPDATE',
    batch,
  })
}

export async function deleteRecords(model: string, keys: string[]) {
  return post<{ ok: boolean }>('/api/record/delete', { model, keys })
}

/** Sheet 新建行编号 */
export async function allocSerials(model: string, count: number, kind?: string) {
  return post<{ codes: string[] }>('/api/record/alloc', {
    model,
    count,
    ...(kind ? { kind } : {}),
  })
}

/** Sheet / 表单公式回填 */
export async function autofillRecord(
  model: string,
  value: Record<string, unknown>,
  using = 'default',
) {
  return post<{ data: Record<string, unknown> }>('/api/record/autofill', {
    model,
    using,
    value,
  })
}

export async function autofillBatch(
  model: string,
  batch: Record<string, unknown>[],
  using = 'default',
) {
  return post<{ data: Record<string, unknown>[] }>('/api/record/autofill', {
    model,
    using,
    batch,
  })
}
