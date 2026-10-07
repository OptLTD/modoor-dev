/** Global shell search: modules register a handler for the current page. */

export type ShellSearchContext = {
  path: string
  moduleId?: string
}

export type ShellSearchHandler = (
  query: string,
  ctx: ShellSearchContext,
) => void | Promise<void>

let handler: ShellSearchHandler | null = null
let ownerId: string | null = null

/** Register search for the active view. Returns unregister. */
export function registerShellSearch(owner: string, fn: ShellSearchHandler): () => void {
  handler = fn
  ownerId = owner
  return () => {
    if (ownerId === owner) {
      handler = null
      ownerId = null
    }
  }
}

export function hasShellSearch(): boolean {
  return handler != null
}

/** Run registered search. Returns false if nothing registered (no-op). */
export function runShellSearch(query: string, ctx: ShellSearchContext): boolean {
  if (!handler) return false
  void handler(query, ctx)
  return true
}
