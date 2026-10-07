import { get, shellLoginUrl, throwHttpError } from './http'

export type UploadedFile = {
  id: string
  filename: string
  title: string
  mime_type: string
}

type AssetPayload = {
  id?: string
  filename?: string
  title?: string
  mime_type?: string
}

type AssetMeta = {
  model?: string
  uukey?: string
  field?: string
  tags?: string[]
}

function toUploaded(asset: AssetPayload, fallbackName = ''): UploadedFile {
  const id = String(asset.id || '').trim()
  if (!id) throw new Error('upload failed')
  return {
    id,
    filename: String(asset.filename || fallbackName || id),
    title: String(asset.title || asset.filename || fallbackName || id),
    mime_type: String(asset.mime_type || ''),
  }
}

export function assetContentUrl(id: string) {
  return `/api/doc/assets/${encodeURIComponent(id)}/content`
}

export async function uploadAsset(
  file: File,
  meta?: AssetMeta,
): Promise<UploadedFile> {
  const body = new FormData()
  body.append('file', file)
  if (file.name) body.append('title', file.name)
  if (meta?.model) body.append('model', meta.model)
  if (meta?.uukey) body.append('uukey', meta.uukey)
  if (meta?.field) body.append('field', meta.field)
  const tags = (meta?.tags || []).map((tag) => tag.trim()).filter(Boolean)
  if (tags.length) body.append('tags', JSON.stringify(tags))
  const res = await fetch('/api/doc/assets', {
    credentials: 'include',
    method: 'POST', body,
  })
  if (res.status === 401) {
    if (!location.pathname.startsWith('/login')) {
      location.href = shellLoginUrl()
    }
    throw new Error('login required')
  }
  if (!res.ok) await throwHttpError(res)
  const data = (await res.json()) as { asset?: AssetPayload }
  return toUploaded(data.asset || {}, file.name)
}

export async function fetchAsset(id: string): Promise<UploadedFile> {
  const url = `/api/doc/assets/${encodeURIComponent(id)}`
  const data = await get<{ asset: AssetPayload }>(url)
  return toUploaded(data.asset || { id }, id)
}
