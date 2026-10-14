/** Company shell settings cached in this browser after /api/base/global. */

import { get, put } from './http'

export type GlobalSettings = {
  locale: 'zh-CN' | 'en-US'
  timezone: string
  timeFormat: string
  defaultModule: string
}

export type GlobalSettingsPayload = {
  settings: GlobalSettings
  canEdit: boolean
  timezones: { id: string; labelZh: string; labelEn: string }[]
  timeFormats: string[]
}

const CACHE_KEY = 'modoor.global'
const LOCALE_KEY = 'modoor.locale'

const DEFAULTS: GlobalSettings = {
  locale: 'zh-CN',
  timezone: 'Asia/Shanghai',
  timeFormat: 'YYYY-MM-DD HH:mm:ss',
  defaultModule: '',
}

function normalizeLocale(raw: string): GlobalSettings['locale'] {
  const v = String(raw || '').trim().toLowerCase()
  if (v === 'en' || v.startsWith('en-') || v === 'us-en') return 'en-US'
  if (v === 'zh' || v.startsWith('zh-')) return 'zh-CN'
  return DEFAULTS.locale
}

export function normalizeGlobalSettings(raw: Partial<GlobalSettings> | null | undefined): GlobalSettings {
  const src = raw || {}
  return {
    locale: normalizeLocale(String(src.locale || '')),
    timezone: String(src.timezone || DEFAULTS.timezone),
    timeFormat: String(src.timeFormat || DEFAULTS.timeFormat),
    defaultModule: String(src.defaultModule || ''),
  }
}

export function readGlobalSettings(): GlobalSettings {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return { ...DEFAULTS }
    return normalizeGlobalSettings(JSON.parse(raw) as Partial<GlobalSettings>)
  } catch {
    return { ...DEFAULTS }
  }
}

export function writeGlobalSettings(raw: Partial<GlobalSettings>): GlobalSettings {
  const next = normalizeGlobalSettings(raw)
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(next))
    localStorage.setItem(LOCALE_KEY, next.locale)
  } catch {
    /* ignore */
  }
  return next
}

export async function fetchGlobalSettings(): Promise<GlobalSettingsPayload> {
  const res = await get<GlobalSettingsPayload>('/api/base/global')
  writeGlobalSettings(res.settings)
  return { ...res, settings: readGlobalSettings() }
}

export async function saveGlobalSettings(settings: GlobalSettings): Promise<GlobalSettingsPayload> {
  const res = await put<GlobalSettingsPayload>('/api/base/global', settings)
  writeGlobalSettings(res.settings)
  return { ...res, settings: readGlobalSettings() }
}
