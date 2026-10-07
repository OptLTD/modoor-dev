import type { SchemaField } from '@modoor/hooks'
import {
  mergeRefers,
  normalizeReferDict,
  referOptions,
  convertReferValue,
  type ReferDict,
} from '@modoor/hooks'

export function normalizeDropdownCellValue(
  f: SchemaField,
  val: string,
  referCache: ReferDict,
): string {
  const s = String(val ?? '').trim()
  if (!s) return ''
  const opts = referOptions(f, referCache)
  if (opts.some((o) => o.value === s)) return s
  const byLabel = opts.find((o) => o.label === s || o.label.trim() === s)
  if (byLabel) return byLabel.value
  const lower = s.toLowerCase()
  const byLabelCi = opts.find((o) => o.label.toLowerCase() === lower)
  return byLabelCi?.value ?? s
}

export function dropdownExcelText(f: SchemaField, val: string, referCache: ReferDict): string {
  const s = String(val ?? '').trim()
  if (!s) return ''
  const opts = referOptions(f, referCache)
  if (opts.some((o) => o.label === s || o.label.trim() === s)) return s
  const text = convertReferValue(f, s, referCache)
  return text.trim() || s
}

export function dropdownSource(
  f: SchemaField,
  referCache: ReferDict,
  extraCellValues: string[] = [],
): { id: string; name: string }[] {
  const map = new Map<string, string>()
  for (const o of referOptions(f, referCache)) {
    if (o.value) map.set(o.value, o.label || o.value)
  }
  for (const raw of extraCellValues) {
    const s = String(raw ?? '').trim()
    if (!s || map.has(s)) continue
    map.set(s, s)
  }
  return [...map.entries()].map(([id, name]) => ({ id, name }))
}

// re-export helpers used elsewhere
export { mergeRefers, normalizeReferDict }
