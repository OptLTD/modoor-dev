/** User shell preferences — per-module menu layout / theme (locale stays in i18n). */

import { computed, ref, type Ref } from 'vue'

export type MenuLayout = 'top' | 'side'
export type ThemePref = 'system' | 'light' | 'dark'

export type UserPrefs = {
  /** Per-module overrides. A missing key follows the tenant module setting. */
  moduleMenus: Record<string, MenuLayout>
  /** Reserved — UI only for now */
  theme: ThemePref
}

const STORAGE_KEY = 'modoor.userPrefs'

const DEFAULTS: UserPrefs = {
  moduleMenus: {},
  theme: 'system',
}

function normalizeMenuLayout(raw: unknown): MenuLayout {
  return raw === 'side' ? 'side' : 'top'
}

function normalizeTheme(raw: unknown): ThemePref {
  if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  return 'system'
}

function normalizeModuleMenus(raw: unknown): Record<string, MenuLayout> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: Record<string, MenuLayout> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    const mid = String(key || '').trim()
    if (!mid) continue
    out[mid] = normalizeMenuLayout(value)
  }
  return out
}

function readStored(): UserPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS, moduleMenus: {} }
    const parsed = JSON.parse(raw) as Partial<UserPrefs> & { menuLayout?: unknown }
    return {
      moduleMenus: normalizeModuleMenus(parsed.moduleMenus),
      theme: normalizeTheme(parsed.theme),
    }
  } catch {
    return { ...DEFAULTS, moduleMenus: {} }
  }
}

function writeStored(prefs: UserPrefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    /* ignore */
  }
}

const prefsRef: Ref<UserPrefs> = ref(readStored())

export function getUserPrefs(): UserPrefs {
  return {
    moduleMenus: { ...prefsRef.value.moduleMenus },
    theme: prefsRef.value.theme,
  }
}

export function moduleMenuOverride(moduleId: string): MenuLayout | null {
  const mid = String(moduleId || '').trim()
  if (!mid) return null
  const raw = prefsRef.value.moduleMenus[mid]
  return raw === 'side' || raw === 'top' ? raw : null
}

export function menuLayoutFor(moduleId: string): MenuLayout {
  return moduleMenuOverride(moduleId) || 'top'
}

export function setModuleMenuLayout(moduleId: string, layout: MenuLayout | null): MenuLayout | null {
  const mid = String(moduleId || '').trim()
  if (!mid) return layout == null ? null : normalizeMenuLayout(layout)
  const current = { ...prefsRef.value.moduleMenus }
  if (layout == null) {
    if (!(mid in current)) return null
    delete current[mid]
  } else {
    const next = normalizeMenuLayout(layout)
    if (current[mid] === next) return next
    current[mid] = next
  }
  prefsRef.value = { ...prefsRef.value, moduleMenus: current }
  writeStored(prefsRef.value)
  return layout == null ? null : current[mid]
}

/** @deprecated Use setModuleMenuLayout — global layout is no longer used. */
export function setMenuLayout(layout: MenuLayout): MenuLayout {
  return normalizeMenuLayout(layout)
}

export function setThemePref(theme: ThemePref): ThemePref {
  const next = normalizeTheme(theme)
  if (prefsRef.value.theme === next) return next
  prefsRef.value = { ...prefsRef.value, theme: next }
  writeStored(prefsRef.value)
  return next
}

export function useUserPrefs() {
  const prefs = computed(() => prefsRef.value)
  const theme = computed(() => prefsRef.value.theme)
  return {
    prefs,
    theme,
    menuLayoutFor,
    moduleMenuOverride,
    setModuleMenuLayout,
    setMenuLayout,
    setThemePref,
  }
}
