import { get, post } from '@modoor/hooks'

export type DocAsset = {
  id: string
  title: string
  filename: string
  mime_type: string
  size_bytes: number
  type: string
  name: string
  tags: string[]
  model?: string
  uukey?: string
  field?: string
  note?: string
  text?: string
  has_text?: boolean
  text_truncated?: boolean
  text_status?: 'pending' | 'running' | 'ready' | 'failed'
  text_method?: string
  text_error?: string
  ext?: string
  created_at?: string | null
  updated_at?: string | null
}

export type TagItem = { tag: string; count: number }
export type ModelItem = { model: string; title?: string; count: number }

export async function listAssets(params?: {
  q?: string
  tag?: string
  model?: string
  tagEmpty?: boolean
  modelEmpty?: boolean
  uukey?: string
  field?: string
  limit?: number
}) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.tag) qs.set('tag', params.tag)
  if (params?.model) qs.set('model', params.model)
  if (params?.tagEmpty) qs.set('tag_empty', '1')
  if (params?.modelEmpty) qs.set('model_empty', '1')
  if (params?.uukey) qs.set('uukey', params.uukey)
  if (params?.field) qs.set('field', params.field)
  if (params?.limit) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs}` : ''
  return get<{ items: DocAsset[]; count: number }>(`/api/doc/assets${suffix}`)
}

export async function getAsset(id: string, opts?: { full?: boolean }) {
  const qs = opts?.full ? '?full=1' : ''
  return get<{ asset: DocAsset }>(`/api/doc/assets/${encodeURIComponent(id)}${qs}`)
}

export type ExcelFilterValue = {
  value: string
  count: number
}

export type ExcelFilter = {
  col: number
  name: string
  values: ExcelFilterValue[]
}

export type ExcelPreview = {
  id: string
  filename: string
  kind: string
  sheet_names: string[]
  sheet: number
  sheet_name: string
  header: string[]
  rows: string[][]
  row_numbers: number[]
  page: number
  page_size: number
  start_row: number
  has_prev: boolean
  has_next: boolean
  filters?: ExcelFilter[]
}

export async function getAssetPreview(
  id: string,
  opts?: {
    sheet?: number
    page?: number
    filters?: Record<string, string[]>
    facets?: boolean
  },
) {
  const qs = new URLSearchParams()
  qs.set('sheet', String(opts?.sheet ?? 0))
  qs.set('page', String(opts?.page ?? 1))
  if (opts?.facets) qs.set('facets', '1')
  const filters = opts?.filters
  if (filters && Object.keys(filters).length) {
    qs.set('filters', JSON.stringify(filters))
  }
  return get<ExcelPreview>(
    `/api/doc/assets/${encodeURIComponent(id)}/preview?${qs}`,
  )
}

export async function listNav() {
  return get<{
    models: ModelItem[]
    model_empty: number
    tags: TagItem[]
    tag_empty: number
  }>('/api/doc/nav')
}

export async function uploadAsset(
  file: File,
  opts?: { title?: string; tags?: string[]; note?: string; model?: string },
) {
  const body = new FormData()
  body.append('file', file)
  if (opts?.title) body.append('title', opts.title)
  if (opts?.tags?.length) body.append('tags', JSON.stringify(opts.tags))
  if (opts?.note) body.append('note', opts.note)
  if (opts?.model) body.append('model', opts.model)
  const res = await fetch('/api/doc/assets', {
    method: 'POST',
    credentials: 'include',
    body,
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; asset: DocAsset }>
}

export async function createTextAsset(body: {
  title: string
  text: string
  tags?: string[]
  note?: string
  filename?: string
}) {
  return post<{ ok: boolean; asset: DocAsset }>('/api/doc/assets/text', body)
}

export async function updateAsset(
  id: string,
  body: { title?: string; tags?: string[]; note?: string; text?: string },
) {
  const res = await fetch(`/api/doc/assets/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<{ ok: boolean; asset: DocAsset }>
}

export async function deleteAsset(id: string) {
  const res = await fetch(`/api/doc/assets/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function contentUrl(id: string, download = false) {
  const qs = download ? '?download=1' : ''
  return `/api/doc/assets/${encodeURIComponent(id)}/content${qs}`
}

export async function fetchContentBlob(id: string) {
  const res = await fetch(contentUrl(id), { credentials: 'include' })
  if (!res.ok) throw new Error(await res.text())
  return res.blob()
}
