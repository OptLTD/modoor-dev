import { get, post } from './http'

/** Special key in module.yaml i18n: module / shell brand title. */
export const APP_LABEL_KEY = 'app.label'

/** Flat messages from module.yaml: { locale: { key: text } }. */
export type ManifestI18n = Partial<Record<string, Record<string, string>>>

export type ShellMenu = {
  id: string
  label: string
  /** Leaf menus have path; groups may omit and use items. */
  path?: string
  /** Sort order (smaller first). */
  seqno?: number
  /** Optional secondary key; lookup uses id first, then key. */
  key?: string
  /** Nested menus rendered as a dropdown group. */
  items?: ShellMenu[]
}

export type ShellModule = {
  id: string
  label: string
  path?: string
  href?: string
  kind?: string
  source?: string
  online?: boolean
  /** Sort order in module switcher / workbench (smaller first). */
  seqno?: number
  /** Flat i18n from module.yaml; `app.label` + keys matching entity id|key. */
  i18n?: ManifestI18n
  menus?: ShellMenu[]
}

export type ShellCatalog = {
  tenant: { id: string; name: string }
  profile: { id: string | number; username: string; realname?: string; tenant: string | number } | null
  modules: ShellModule[]
}

export async function fetchShellCatalog() {
  return get<ShellCatalog>('/api/shell/modules')
}

/**
 * Resolve a message from module flat i18n.
 * Lookup order: locale[key] → en-US[key] → fallback.
 */
export function resolveManifestText(
  messages: ManifestI18n | null | undefined,
  key: string,
  locale: string,
  fallback = '',
): string {
  const k = String(key || '').trim()
  if (!k || !messages) return fallback
  const loc = String(locale || '')
  const primary = messages[loc]?.[k]
  if (primary) return primary
  if (loc !== 'en-US') {
    const en = messages['en-US']?.[k]
    if (en) return en
  }
  return fallback
}

/** Module brand label: special key `app.label`, else ui-web label. */
export function localizedAppLabel(
  mod: Pick<ShellModule, 'label' | 'i18n'> | null | undefined,
  locale: string,
  fallback = '',
): string {
  if (!mod) return fallback
  return resolveManifestText(mod.i18n, APP_LABEL_KEY, locale, mod.label || fallback)
}

/**
 * Generic entity label: bind i18n by `id` or `key`.
 * Tries id first, then key, then item.label.
 */
export function localizedEntityLabel(
  messages: ManifestI18n | null | undefined,
  item: { id?: string; key?: string; label?: string } | null | undefined,
  locale: string,
  fallback = '',
): string {
  if (!item) return fallback
  const id = String(item.id || '').trim()
  const key = String(item.key || '').trim()
  if (id) {
    const hit = resolveManifestText(messages, id, locale, '')
    if (hit) return hit
  }
  if (key && key !== id) {
    const hit = resolveManifestText(messages, key, locale, '')
    if (hit) return hit
  }
  return item.label || fallback
}
