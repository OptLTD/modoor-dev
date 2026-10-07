/** Global interceptors for SchemaView row / relation clicks. */

export type RecordHandlePayload = {
  model?: string
  uukey?: string
  title?: string
  record?: Record<string, unknown>
  lookup?: Record<string, unknown>
  intent?: 'detail' | 'modify'
  using?: string
  click?: { uukey?: string; action?: string; using?: string }
}

export type RecordHandle = (payload: RecordHandlePayload) => boolean | void

type Entry = { key: string; fn: RecordHandle }

const registry = new Map<string, Entry[]>()

/** Register an interceptor. The same key replaces a previous registration (HMR-safe). */
export function registerRecordHandle(
  action: string,
  fn: RecordHandle,
  key = 'default',
): void {
  const list = (registry.get(action) || []).filter((e) => e.key !== key)
  list.push({ key, fn })
  registry.set(action, list)
}

/** First handler that returns true consumes the action. */
export function invokeRecordHandles(action: string, payload: RecordHandlePayload): boolean {
  for (const entry of registry.get(action) || []) {
    if (entry.fn(payload) === true) return true
  }
  return false
}
