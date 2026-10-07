import { fetchSchema } from './record'

const cache = new Map<string, string>()

/** Strip list/admin suffixes so "车辆管理" → "车辆". */
export function entityLabel(title: string, fallback = ''): string {
  const raw = String(title || '').trim()
  if (!raw) return fallback
  const short = raw.replace(/(管理|列表|维护)$/u, '').trim()
  return short || raw
}

export async function resolveModelTitle(model: string, hint = ''): Promise<string> {
  const key = String(model || '').trim()
  if (!key) return hint
  if (hint) {
    cache.set(key, hint)
    return hint
  }
  const hit = cache.get(key)
  if (hit) return hit
  try {
    const res = await fetchSchema(key, 'default', 'SEARCH')
    const title = String(res.table?.title || key).trim() || key
    cache.set(key, title)
    return title
  } catch {
    cache.set(key, key)
    return key
  }
}

export function rememberModelTitle(model: string, title: string) {
  const key = String(model || '').trim()
  const label = String(title || '').trim()
  if (key && label) cache.set(key, label)
}
