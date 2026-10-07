import { get, post } from './http'

export type AuthTenant = {
  id: number | string
  name: string
}

export type AuthUser = {
  id: number | string
  uukey?: string
  username: string
  realname?: string
  tenant?: number | string
  current?: number | string | null
  base_id?: number | string
  tenants?: AuthTenant[]
}

export type AgentConnectInfo = {
  mcp_url: string
  auth_url?: string
  oauth_issuer?: string
  agent_readme?: string
  agent_brief?: string
  agent_skills?: string
  agent_key: string
  agent_readonly: boolean
  tenant: number | string
  user_id: number | string
  header: string
  alt_header: string
  hint?: string
  snippet: Record<string, unknown>
  snippet_with_key?: Record<string, unknown>
}

export async function login(username: string, password: string) {
  return post<{ ok: boolean; user: AuthUser; module?: string; home?: string }>(
    '/api/auth/login',
    {
      username,
      password,
    },
  )
}

export async function fetchProfile() {
  return get<{ user: AuthUser }>('/api/auth/profile')
}

export async function fetchAgentConnect() {
  return get<AgentConnectInfo>('/api/auth/agent-connect')
}

export async function rotateAgentKey() {
  return post<{ ok: boolean; agent_key: string; agent_readonly?: boolean }>(
    '/api/auth/agent-key/rotate',
    {},
  )
}

export async function setAgentReadonly(readonly: boolean) {
  return post<{ ok: boolean; agent_readonly: boolean }>('/api/auth/agent-readonly', {
    readonly,
  })
}

export async function switchTenant(tenantId: number | string) {
  return post<{ ok: boolean; user: AuthUser; module?: string; home?: string }>(
    '/api/auth/switch',
    {
      tenant_id: Number(tenantId),
    },
  )
}

export async function logout() {
  return post<{ ok: boolean }>('/api/auth/logout', {})
}
