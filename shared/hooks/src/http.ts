import { t } from './i18n'

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: { Accept: 'application/json' },
  }
  if (body !== undefined) {
    init.headers = {
      ...init.headers,
      'Content-Type': 'application/json',
    }
    init.body = JSON.stringify(body)
  }
  const res = await fetch(url, init)
  if (res.status === 401) {
    redirectToLogin()
    throw new Error('login required')
  }
  if (!res.ok) {
    await throwHttpError(res)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  return request<T>('POST', url, body ?? {})
}

export async function get<T>(url: string): Promise<T> {
  return request<T>('GET', url)
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  return request<T>('PUT', url, body ?? {})
}

export async function throwHttpError(res: Response): Promise<never> {
  const text = await res.text()
  throw new Error(apiErrorMessage(text, res.statusText))
}

/** Pull FastAPI `{detail:{message}}` (or similar) and map known conflicts. */
export function apiErrorMessage(raw: string, fallback = ''): string {
  const text = (raw || '').trim()
  const extracted = extractApiMessage(text) || fallback || text
  return friendlyApiMessage(extracted)
}

function extractApiMessage(text: string): string | null {
  if (!text) return null
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      const data = JSON.parse(text) as Record<string, unknown>
      const detail = data.detail ?? data.error ?? data
      if (typeof detail === 'string' && detail.trim()) return detail.trim()
      if (detail && typeof detail === 'object') {
        const obj = detail as Record<string, unknown>
        const msg = obj.message ?? obj.msg ?? obj.detail
        if (typeof msg === 'string' && msg.trim()) return msg.trim()
      }
    } catch {
      /* not json */
    }
  }
  return text
}

function friendlyApiMessage(msg: string): string {
  const email = msg.match(/^email already exists:\s*(.*)$/i)
  if (email) return t('common.emailExists', { email: email[1] })
  const phone = msg.match(/^phone already exists:\s*(.*)$/i)
  if (phone) return t('common.phoneExists', { phone: phone[1] })
  const user = msg.match(/^username already exists:\s*(.*)$/i)
  if (user) return t('common.usernameExists', { username: user[1] })
  if (/^email or phone is required$/i.test(msg)) return t('common.emailOrPhoneRequired')
  return msg
}

/** Login URL — same-origin `/login` when behind API proxy; optional VITE_SHELL_URL. */
export function shellLoginUrl(next?: string): string {
  const shell = (import.meta as ImportMeta & { env: Record<string, string> }).env
    ?.VITE_SHELL_URL
  const base = (shell || '').replace(/\/$/, '')
  const target = next || `${location.pathname}${location.search}`
  const q = `next=${encodeURIComponent(target.startsWith('http') ? target : location.href)}`
  if (base) return `${base}/login?${q}`
  return `/login?${q}`
}

function redirectToLogin() {
  if (location.pathname.startsWith('/login')) return
  location.href = shellLoginUrl()
}
