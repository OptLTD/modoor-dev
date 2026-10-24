import { useCallback, useSyncExternalStore } from 'react'
import {
  getLocale,
  setLocale,
  subscribeLocale,
  t as translate,
  type LocaleCode,
  SUPPORTED_LOCALES,
} from '@modoor/hooks/i18n'

export function useI18n() {
  const locale = useSyncExternalStore(subscribeLocale, getLocale, getLocale)
  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      void locale
      return translate(key, params)
    },
    [locale],
  )
  return { locale, t, setLocale: (code: string) => setLocale(code), SUPPORTED_LOCALES }
}

export type { LocaleCode }
