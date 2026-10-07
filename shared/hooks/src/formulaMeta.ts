import type { SchemaField } from './record'
import { fieldKey } from './recordPayload'

export function extraHasFormula(extra: SchemaField['extra']): boolean {
  if (!extra) return false
  const f = extra.formula
  if (f != null && f !== '') {
    if (typeof f === 'boolean') return f
    if (String(f).trim() !== '') return true
  }
  const d = extra.display
  return typeof d === 'string' && d.includes('[') && d.includes(']')
}

export function dependsIncludesTrigger(depends: unknown, triggerUukey: string): boolean {
  if (!Array.isArray(depends) || !triggerUukey) return false
  return depends.some((d) => d === triggerUukey || String(d) === triggerUukey)
}

/** 被依赖源变化后需要写回：depends 含本次触发列（含公式产物） */
export function shouldSyncAutofillColumn(f: SchemaField, triggerUukey: string): boolean {
  const extra = f.extra
  if (!extra) return false
  return dependsIncludesTrigger(extra.depends, triggerUukey)
}

/**
 * 变更后需要跑 autofill 的源字段 uukey（去重）。
 * 在所有列 depends 基础上，沿各列自己的 depends 向上递推。
 */
export function buildDependsTriggers(fields: SchemaField[]): string[] {
  const byUukey = new Map<string, SchemaField>()
  for (const f of fields) {
    const k = fieldKey(f)
    if (k) byUukey.set(k, f)
    if (f.uukey) byUukey.set(f.uukey, f)
  }
  const triggers = new Set<string>()
  const queue: string[] = []
  const enqueue = (uu: string) => {
    const k = String(uu).trim()
    if (!k || triggers.has(k)) return
    triggers.add(k)
    queue.push(k)
  }
  for (const item of fields) {
    const depends = item.extra?.depends
    if (!Array.isArray(depends)) continue
    for (const d of depends) {
      enqueue(String(d))
    }
  }
  let qi = 0
  while (qi < queue.length) {
    const u = queue[qi++]
    const col = byUukey.get(u)
    const upDepends = col?.extra?.depends
    if (!Array.isArray(upDepends)) continue
    for (const up of upDepends) {
      enqueue(String(up))
    }
  }
  return [...triggers]
}
