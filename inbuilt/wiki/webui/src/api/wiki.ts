async function parse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    const next = encodeURIComponent(location.href)
    location.href = `/login?next=${next}`
    throw new Error('unauthorized')
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include' })
  return parse<T>(res)
}

export async function apiSend<T>(
  path: string,
  method: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return parse<T>(res)
}

export type WikiProject = {
  id: string
  name: string
  description: string
  home_page_id: string | null
  updated_at?: string | null
}

export type WikiPage = {
  id: string
  project_id: string
  parent_id: string | null
  sort_order: number
  title: string
  body?: string
  updated_at?: string | null
}

export type TreeNode = {
  id: string
  title: string
  sort_order: number
  parent_id: string | null
  children: TreeNode[]
}

export function listProjects() {
  return apiGet<{ items: WikiProject[]; count: number }>('/api/wiki/projects')
}

export function createProject(body: { name: string; description?: string; home_title?: string }) {
  return apiSend<{ ok: boolean; project: WikiProject; home_page: WikiPage }>(
    '/api/wiki/projects',
    'POST',
    body,
  )
}

export function updateProject(id: string, body: { name?: string; description?: string }) {
  return apiSend<{ ok: boolean; project: WikiProject }>(`/api/wiki/projects/${id}`, 'PATCH', body)
}

export function deleteProject(id: string) {
  return apiSend<{ ok: boolean }>(`/api/wiki/projects/${id}`, 'DELETE')
}

export function getProject(id: string) {
  return apiGet<{ project: WikiProject }>(`/api/wiki/projects/${id}`)
}

export function getTree(projectId: string) {
  return apiGet<{ project_id: string; home_page_id: string | null; tree: TreeNode[] }>(
    `/api/wiki/projects/${projectId}/tree`,
  )
}

export function getPage(id: string) {
  return apiGet<{ page: WikiPage }>(`/api/wiki/pages/${id}`)
}

export function createPage(body: {
  project_id: string
  title: string
  parent_id?: string | null
  body?: string
}) {
  return apiSend<{ ok: boolean; page: WikiPage }>('/api/wiki/pages', 'POST', body)
}

export function updatePage(id: string, body: { title?: string; body?: string }) {
  return apiSend<{ ok: boolean; page: WikiPage }>(`/api/wiki/pages/${id}`, 'PATCH', body)
}

export function movePage(id: string, body: { parent_id?: string | null; sort_order?: number }) {
  return apiSend<{ ok: boolean; page: WikiPage }>(`/api/wiki/pages/${id}/move`, 'POST', body)
}

export function deletePage(id: string) {
  return apiSend<{ ok: boolean }>(`/api/wiki/pages/${id}`, 'DELETE')
}

export async function fetchProfile() {
  return apiGet<{ user: { id: number | string; username: string; realname?: string; tenant?: number | string } }>(
    '/api/auth/profile',
  )
}

export async function fetchShellModules() {
  return apiGet<{
    tenant?: { id: string; name: string }
    modules: {
      id: string
      label: string
      href?: string
      path?: string
      i18n?: Record<string, Record<string, string>>
      menus?: { id: string; label: string; path: string; key?: string }[]
    }[]
  }>('/api/shell/modules')
}

export async function logout() {
  return apiSend('/api/auth/logout', 'POST', {})
}
