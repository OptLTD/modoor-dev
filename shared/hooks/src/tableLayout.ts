/**
 * 模块默认表格列宽 — base_cfg: mod=<module> · type=table.layout
 * data: { [model]: { [using]: { widths: { [fieldUukey]: px } } } }
 * 列顺序与隐藏列在 base_tbl，不写这里。
 */
import { get, put } from './http'

export const TABLE_LAYOUT_TYPE = 'table.layout'
export const ACTION_WIDTH_KEY = '__action__'

export type TableViewLayout = {
  widths: Record<string, number>
}

/** model → using → layout */
export type TableLayoutData = Record<string, Record<string, TableViewLayout>>

const cache = new Map<string, TableLayoutData>()
const inflight = new Map<string, Promise<TableLayoutData>>()
const saveTimers = new Map<string, ReturnType<typeof setTimeout>>()

export function modFromModel(model: string): string {
  const m = String(model || '').trim()
  if (!m) return ''
  const i = m.indexOf('.')
  return i > 0 ? m.slice(0, i) : m
}

function parseWidths(raw: unknown): Record<string, number> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const widths: Record<string, number> = {}
  for (const [fk, w] of Object.entries(raw as Record<string, unknown>)) {
    const key = String(fk || '').trim()
    if (!key || key === 'columns' || key === 'widths') continue
    const n = Math.round(Number(w))
    if (!Number.isFinite(n) || n < 40) continue
    widths[key] = n
  }
  return widths
}

export function normalizeTableLayout(raw: unknown): TableLayoutData {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: TableLayoutData = {}
  for (const [model, views] of Object.entries(raw as Record<string, unknown>)) {
    const mk = String(model || '').trim()
    if (!mk || !views || typeof views !== 'object' || Array.isArray(views)) continue
    const viewOut: Record<string, TableViewLayout> = {}
    for (const [using, meta] of Object.entries(views as Record<string, unknown>)) {
      const uk = String(using || '').trim() || 'default'
      if (!meta || typeof meta !== 'object' || Array.isArray(meta)) continue
      const obj = meta as { widths?: unknown }
      const structured = 'widths' in obj
      const widths = parseWidths(structured ? obj.widths : obj)
      if (!Object.keys(widths).length) continue
      viewOut[uk] = { widths }
    }
    if (Object.keys(viewOut).length) out[mk] = viewOut
  }
  return out
}

export function viewWidths(
  data: TableLayoutData | null | undefined,
  model: string,
  using = 'default',
): Record<string, number> {
  const m = String(model || '').trim()
  const u = String(using || '').trim() || 'default'
  if (!m || !data) return {}
  const views = data[m]
  if (!views) return {}
  const hit = views[u] || views.default
  return hit?.widths ? { ...hit.widths } : {}
}

export async function fetchTableLayout(mod: string): Promise<TableLayoutData> {
  const m = String(mod || '').trim()
  if (!m) return {}
  if (cache.has(m)) return cache.get(m)!
  const pending = inflight.get(m)
  if (pending) return pending
  const job = (async () => {
    try {
      const res = await get<{ item: { data?: unknown } | null }>(
        `/api/base/config/item?mod=${encodeURIComponent(m)}&type=${encodeURIComponent(TABLE_LAYOUT_TYPE)}`,
      )
      const data = normalizeTableLayout(res.item?.data)
      cache.set(m, data)
      return data
    } catch {
      const empty: TableLayoutData = {}
      cache.set(m, empty)
      return empty
    } finally {
      inflight.delete(m)
    }
  })()
  inflight.set(m, job)
  return job
}

export async function saveTableLayout(mod: string, data: TableLayoutData): Promise<void> {
  const m = String(mod || '').trim()
  if (!m) return
  const normalized = normalizeTableLayout(data)
  cache.set(m, normalized)
  await put('/api/base/config', {
    mod: m,
    type: TABLE_LAYOUT_TYPE,
    title: '表格布局',
    data: normalized,
  })
}

function ensureView(data: TableLayoutData, model: string, using: string): TableViewLayout {
  if (!data[model]) data[model] = {}
  if (!data[model][using]) data[model][using] = { widths: {} }
  return data[model][using]
}

function scheduleSave(mod: string, debounceMs = 400) {
  const prev = saveTimers.get(mod)
  if (prev) clearTimeout(prev)
  saveTimers.set(
    mod,
    setTimeout(() => {
      saveTimers.delete(mod)
      void saveTableLayout(mod, cache.get(mod) || {})
    }, debounceMs),
  )
}

/** 写入某 model/using 下一列宽，debounce 后整包 PUT */
export function patchTableWidth(
  model: string,
  using: string,
  fieldKey: string,
  width: number,
  opts?: { debounceMs?: number },
) {
  const mod = modFromModel(model)
  const fk = String(fieldKey || '').trim()
  if (!mod || !fk) return
  const m = String(model || '').trim()
  const u = String(using || '').trim() || 'default'
  const w = Math.max(40, Math.round(width))
  const cur = normalizeTableLayout(cache.get(mod) || {})
  ensureView(cur, m, u).widths[fk] = w
  cache.set(mod, cur)
  scheduleSave(mod, opts?.debounceMs ?? 400)
}

export function clearTableLayoutCache(mod?: string) {
  if (mod) {
    cache.delete(mod)
    inflight.delete(mod)
    return
  }
  cache.clear()
  inflight.clear()
}
