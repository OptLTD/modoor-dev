import { get, post, throwHttpError } from '@modoor/hooks'

export type User = {
  id: number
  uukey?: string
  base_id?: number
  username: string
  realname: string
  name?: string
  phone?: string | null
  remark?: string | null
  current?: number | null
  email?: string | null
  active: boolean
  team_id: number
}

export type TeamNode = {
  id: number
  name: string
  parent?: number | null
  seqno: number
  active: boolean
  children: TeamNode[]
}

export async function listUsers(params?: { q?: string; team_id?: number | null }) {
  const qs = new URLSearchParams()
  if (params?.q) qs.set('q', params.q)
  if (params?.team_id != null) qs.set('team_id', String(params.team_id))
  const suffix = qs.toString() ? `?${qs}` : ''
  return get<{ items: User[] }>(`/api/base/users${suffix}`)
}

export async function createUser(body: {
  username: string
  realname: string
  email?: string
  password?: string
  team_id?: number
}) {
  return post<{ ok: boolean; user: User }>('/api/base/users', body)
}

export async function updateUser(
  userKey: number | string,
  body: {
    realname?: string
    email?: string
    active?: boolean
    password?: string
    team_id?: number
  },
) {
  const res = await fetch(`/api/base/users/${encodeURIComponent(String(userKey))}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) await throwHttpError(res)
  return res.json() as Promise<{ ok: boolean; user: User }>
}

export async function deleteUser(userKey: number | string) {
  const res = await fetch(`/api/base/users/${encodeURIComponent(String(userKey))}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) await throwHttpError(res)
  return res.json()
}

export async function listTeamTree() {
  return get<{ tree: TeamNode[]; count: number }>('/api/base/teams/tree')
}

export async function createTeam(body: { name: string; parent?: number | null }) {
  return post<{ ok: boolean; team: TeamNode }>('/api/base/teams', body)
}

export async function updateTeam(
  teamId: number,
  body: { name?: string; parent?: number | null; active?: boolean },
) {
  const res = await fetch(`/api/base/teams/${teamId}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) await throwHttpError(res)
  return res.json() as Promise<{ ok: boolean; team: TeamNode }>
}

export async function deleteTeam(teamId: number) {
  const res = await fetch(`/api/base/teams/${teamId}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) await throwHttpError(res)
  return res.json()
}

export async function rolesBundle() {
  return get<{
    roles: { id: string; code: string; name: string; description?: string | null }[]
    users: User[]
    assignments: Record<string, { id: string; code: string }[]>
    role_nodes: Record<string, string[]>
    ability_catalog: {
      modules: {
        module_id: string
        label: string
        i18n?: Record<string, Record<string, string>>
        abilities: string[]
      }[]
      abilities: string[]
      count: number
    }
  }>('/api/base/roles')
}

export async function setRoleNodes(roleId: string, nodes: string[]) {
  const res = await fetch(`/api/base/roles/${roleId}/nodes`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ nodes }),
  })
  if (!res.ok) await throwHttpError(res)
  return res.json() as Promise<{ role_id: string; nodes: string[]; count: number }>
}

export async function createRole(body: {
  name: string
  code?: string
  description?: string
}) {
  return post<{ ok: boolean; role: { id: string; code: string; name: string } }>(
    '/api/base/roles',
    body,
  )
}

export async function deleteRole(roleId: string) {
  const res = await fetch(`/api/base/roles/${roleId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) await throwHttpError(res)
  return res.json()
}

export async function fetchUserRoles(userKey: number | string) {
  return get<{
    ok: boolean
    user_id: number
    roles: { id: string; code: string; name: string; description?: string | null }[]
    assigned: { id: string; code: string; name: string }[]
  }>(`/api/base/users/${encodeURIComponent(String(userKey))}/roles`)
}

export async function assignRole(user_id: number, role_id: string) {
  return post('/api/base/roles/assign', { user_id, role_id })
}

export async function revokeRole(user_id: number, role_id: string) {
  return post('/api/base/roles/revoke', { user_id, role_id })
}

export type ModuleItem = {
  id: string
  label?: string
  kind?: string
  version?: string
  summary?: string
  tags?: string[]
  risk_default?: string
  enabled: boolean
  online?: boolean
  source?: string
  origin?: 'lightapp' | 'builtin' | 'addon' | string
  pkg?: string
  tools?: string[]
  skills?: string[]
}

export async function listModules() {
  return get<{ modules: ModuleItem[] }>('/api/base/modules')
}

export async function toggleModule(moduleId: string, enabled: boolean) {
  return post(`/api/base/modules/${moduleId}/toggle`, { enabled })
}
