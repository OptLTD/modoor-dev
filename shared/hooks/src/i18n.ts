/** Lightweight i18n — zh-CN / en-US, fallback en-US. */

import { computed, ref, type Ref } from 'vue'

export type LocaleCode = 'zh-CN' | 'en-US'

export type MessageTree = { [key: string]: string | MessageTree }

const FALLBACK: LocaleCode = 'en-US'
const STORAGE_KEY = 'modoor.locale'

const catalogs = new Map<string, Partial<Record<LocaleCode, MessageTree>>>()

const localeRef: Ref<LocaleCode> = ref(detectInitial())

function detectInitial(): LocaleCode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return normalizeLocale(saved)
  } catch {
    /* ignore */
  }
  try {
    const nav = (navigator.language || '').toLowerCase()
    if (nav.startsWith('zh')) return 'zh-CN'
  } catch {
    /* ignore */
  }
  return FALLBACK
}

/** Accept zh-cn / zh-CN / us-en / en-US / en … */
export function normalizeLocale(raw: string | null | undefined): LocaleCode {
  const v = String(raw || '')
    .trim()
    .toLowerCase()
    .replace(/_/g, '-')
  if (!v) return FALLBACK
  if (v === 'zh' || v.startsWith('zh-')) return 'zh-CN'
  if (v === 'us-en' || v === 'en-us' || v === 'en' || v.startsWith('en-')) return 'en-US'
  return FALLBACK
}

export function getLocale(): LocaleCode {
  return localeRef.value
}

export function setLocale(raw: string): LocaleCode {
  const next = normalizeLocale(raw)
  if (next === localeRef.value) return next
  localeRef.value = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    /* ignore */
  }
  try {
    document.documentElement.lang = next
  } catch {
    /* ignore */
  }
  for (const cb of localeListeners) {
    try {
      cb()
    } catch {
      /* ignore */
    }
  }
  return next
}

const localeListeners = new Set<() => void>()

/** For React / non-Vue: subscribe to locale changes. */
export function subscribeLocale(listener: () => void): () => void {
  localeListeners.add(listener)
  return () => {
    localeListeners.delete(listener)
  }
}

export function registerMessages(
  namespace: string,
  messages: Partial<Record<LocaleCode, MessageTree>>,
): void {
  const prev = catalogs.get(namespace) || {}
  catalogs.set(namespace, {
    'en-US': deepMerge(prev['en-US'] || {}, messages['en-US'] || {}),
    'zh-CN': deepMerge(prev['zh-CN'] || {}, messages['zh-CN'] || {}),
  })
  // bump reactivity so open UIs refresh after late registration
  localeRef.value = localeRef.value
  for (const cb of localeListeners) {
    try {
      cb()
    } catch {
      /* ignore */
    }
  }
}

function deepMerge(a: MessageTree, b: MessageTree): MessageTree {
  const out: MessageTree = { ...a }
  for (const [k, v] of Object.entries(b)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const cur = out[k]
      out[k] = deepMerge(
        cur && typeof cur === 'object' && !Array.isArray(cur) ? cur : {},
        v as MessageTree,
      )
    } else {
      out[k] = v
    }
  }
  return out
}

function lookup(tree: MessageTree | undefined, path: string[]): string | undefined {
  if (!tree) return undefined
  let cur: string | MessageTree | undefined = tree
  for (const p of path) {
    if (!cur || typeof cur === 'string') return undefined
    cur = cur[p]
  }
  return typeof cur === 'string' ? cur : undefined
}

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) =>
    params[key] != null ? String(params[key]) : `{${key}}`,
  )
}

/**
 * Translate key. Format `namespace.path.to.key`.
 * Missing → fallback en-US → key itself.
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const parts = key.split('.').filter(Boolean)
  if (parts.length < 2) return key
  const ns = parts[0]
  const path = parts.slice(1)
  const pack = catalogs.get(ns)
  const loc = localeRef.value
  const primary = lookup(pack?.[loc], path)
  if (primary != null) return interpolate(primary, params)
  if (loc !== FALLBACK) {
    const fb = lookup(pack?.[FALLBACK], path)
    if (fb != null) return interpolate(fb, params)
  }
  return key
}

/** Reactive helper for Vue SFCs. */
export function useI18n() {
  const locale = computed(() => localeRef.value)
  function tr(key: string, params?: Record<string, string | number>) {
    void localeRef.value
    return t(key, params)
  }
  return { locale, t: tr, setLocale, normalizeLocale }
}

export const SUPPORTED_LOCALES: { code: LocaleCode; label: string }[] = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en-US', label: 'English' },
]

export { localeRef }

// apply html lang on load
try {
  document.documentElement.lang = localeRef.value
} catch {
  /* ignore */
}
