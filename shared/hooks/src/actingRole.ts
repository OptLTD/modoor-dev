/** Browser-only acting role. Keyed by user so two accounts on one browser do not share it. */

export const SUPERUSER_CODE = 'SUPERUSER'
const USER_KEY = 'modoor.activeRoleUser'
const ROLE_COOKIE = 'modoor_role'
const CHOSEN_PREFIX = 'modoor.activeRoleChosen:'

export type SwitchRole = {
  code: string
  name: string
}

export function actingRoleStorageKey(userId: string | number) {
  return `modoor.activeRole:${userId}`
}

function chosenKey(userId: string | number) {
  return `${CHOSEN_PREFIX}${userId}`
}

export function readActingRole(): string {
  if (typeof localStorage === 'undefined') return ''
  const userId = localStorage.getItem(USER_KEY) || ''
  if (!userId) return ''
  return localStorage.getItem(actingRoleStorageKey(userId)) || ''
}

export function readRoleCookie(): string {
  if (typeof document === 'undefined') return ''
  const matched = document.cookie.match(/(?:^|; )modoor_role=([^;]*)/)
  return matched ? decodeURIComponent(matched[1]) : ''
}

export function writeActingRole(userId: string | number, code: string) {
  if (typeof localStorage === 'undefined') return
  const next = String(code || '').trim()
  localStorage.setItem(USER_KEY, String(userId))
  localStorage.setItem(actingRoleStorageKey(userId), next)
  localStorage.setItem(chosenKey(userId), '1')
  if (typeof document === 'undefined') return
  const secure = location.protocol === 'https:' ? '; Secure' : ''
  if (!next) {
    document.cookie = `${ROLE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${secure}`
    return
  }
  document.cookie = `${ROLE_COOKIE}=${encodeURIComponent(next)}; Path=/; SameSite=Lax${secure}`
}

export function clearActingRole() {
  if (typeof localStorage !== 'undefined') {
    const userId = localStorage.getItem(USER_KEY)
    if (userId) {
      localStorage.removeItem(actingRoleStorageKey(userId))
      localStorage.removeItem(chosenKey(userId))
    }
    localStorage.removeItem(USER_KEY)
  }
  if (typeof document === 'undefined') return
  document.cookie = `${ROLE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`
}

/**
 * Cached choice when it is still in the list.
 * Superuser defaults to SUPERUSER (full access), not the first business role.
 * An explicit empty choice stays empty — except when SUPERUSER is the only option.
 */
export function resolveActingRole(userId: string | number, roles: SwitchRole[]): string {
  const hasSuper = roles.some((role) => role.code === SUPERUSER_CODE)
  const onlySuper = roles.length === 1 && hasSuper
  if (typeof localStorage === 'undefined') {
    return hasSuper ? SUPERUSER_CODE : ''
  }
  const cached = localStorage.getItem(actingRoleStorageKey(userId)) || ''
  if (cached && roles.some((role) => role.code === cached)) return cached
  if (onlySuper) return SUPERUSER_CODE
  if (!cached && localStorage.getItem(chosenKey(userId)) === '1') return ''
  return hasSuper ? SUPERUSER_CODE : ''
}
