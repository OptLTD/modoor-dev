/** Global interceptors for SchemaView actions that are not built-in. */

export type RecordHandlePayload = {
  model?: string
  /** Clicked identity: the row key, or the relation cell's key. */
  uukey?: string
  title?: string
  /** Rows currently visible in the list. */
  records?: Record<string, unknown>[]
  /** Checked rows. Toolbar buttons read this. */
  selected?: Record<string, unknown>[]
  /** The row of an inline button or a cell click. */
  current?: Record<string, unknown>
  lookup?: Record<string, unknown>
  intent?: 'detail' | 'modify'
  using?: string
  click?: {
    uukey?: string
    action?: string
    label?: string
    using?: string
    extra?: Record<string, unknown>
  }
}

/** List-page abilities. SchemaView exposes these; handles receive them beside the click payload. */
export type RecordView = {
  openForm: (form: {
    model: string
    using?: string
    title?: string
    defaults?: Record<string, unknown>
  }) => void
  /** 下钻到另一模型的 TableDrawer（按 query 过滤）。 */
  openTable?: (table: {
    model: string
    using?: string
    title?: string
    query?: Record<string, unknown>
    fields?: string[]
  }) => void
  reload: () => Promise<void>
}

export type RecordHandle = (
  payload: RecordHandlePayload,
  view: RecordView,
) => boolean | void | Promise<boolean | void>

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
export async function invokeRecordHandles(
  action: string,
  payload: RecordHandlePayload,
  view: RecordView,
): Promise<boolean> {
  for (const entry of registry.get(action) || []) {
    if ((await entry.fn(payload, view)) === true) return true
  }
  return false
}
