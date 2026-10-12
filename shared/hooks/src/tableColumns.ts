/**
 * 列表列设置 — base_tbl，level 固定 global。
 * data: { order, hidden, filterOrder?, filterHidden? }
 */
import { get, put } from './http'

export type TableColumnLayout = {
  order: string[]
  hidden: string[]
  filterOrder?: string[]
  filterHidden?: string[]
}

const cache = new Map<string, TableColumnLayout | null>()
const saveTimers = new Map<string, ReturnType<typeof setTimeout>>()

function viewKey(model: string, using: string): string {
  return `${String(model || '').trim()}\n${String(using || '').trim() || 'default'}`
}

function parseKeys(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const key = String(item ?? '').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(key)
  }
  return out
}

export function parseTableColumns(raw: unknown): TableColumnLayout | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const obj = raw as {
    order?: unknown
    hidden?: unknown
    filterOrder?: unknown
    filterHidden?: unknown
  }
  const order = parseKeys(obj.order)
  const hidden = parseKeys(obj.hidden)
  const filterOrder = parseKeys(obj.filterOrder)
  const filterHidden = parseKeys(obj.filterHidden)
  if (!order.length && !hidden.length && !filterOrder.length && !filterHidden.length) return null
  const out: TableColumnLayout = { order, hidden }
  if (filterOrder.length || filterHidden.length) {
    out.filterOrder = filterOrder
    out.filterHidden = filterHidden
  }
  return out
}

export async function fetchTableColumns(
  model: string,
  using = 'default',
): Promise<TableColumnLayout | null> {
  const m = String(model || '').trim()
  const u = String(using || '').trim() || 'default'
  if (!m) return null
  const key = viewKey(m, u)
  if (cache.has(key)) return cache.get(key) ?? null
  try {
    const res = await get<{ item: { data?: unknown } | null }>(
      `/api/base/tbl?model=${encodeURIComponent(m)}&using=${encodeURIComponent(u)}`,
    )
    const data = parseTableColumns(res.item?.data)
    cache.set(key, data)
    return data
  } catch {
    return null
  }
}

/** 写入列/快捷筛选布局。columns 为 null 时删除记录，恢复 tables.json 默认。 */
export function saveTableColumns(
  model: string,
  using: string,
  columns: TableColumnLayout | null,
  opts?: { debounceMs?: number },
) {
  const m = String(model || '').trim()
  const u = String(using || '').trim() || 'default'
  if (!m) return
  const key = viewKey(m, u)
  const next = columns ? parseTableColumns(columns) : null
  cache.set(key, next)
  const prev = saveTimers.get(key)
  if (prev) clearTimeout(prev)
  const ms = opts?.debounceMs ?? 400
  saveTimers.set(
    key,
    setTimeout(() => {
      saveTimers.delete(key)
      void put('/api/base/tbl', { model: m, using: u, data: cache.get(key) })
    }, ms),
  )
}
