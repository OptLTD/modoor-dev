/** Current user's ability gate, from the shell catalog or a schema response. */
export type AccessGate = {
  unrestricted?: boolean
  abilities?: string[]
}

type Gated = {
  access?: string[]
}

let cachedGate: AccessGate | undefined

export function rememberAccess(gate: AccessGate | undefined) {
  cachedGate = gate
}

export function cachedAccess() {
  return cachedGate
}

/**
 * A control is visible when it declares no access, the user is unrestricted,
 * or they hold any listed ability. Missing gate means the payload has no
 * permission info yet, so nothing is hidden.
 */
export function accessAllows(required: string[] | undefined | null, gate?: AccessGate | null): boolean {
  const need = (required || []).map((code) => String(code).trim()).filter(Boolean)
  if (!need.length) return true
  if (!gate) return true
  if (gate.unrestricted) return true
  const have = new Set(gate.abilities || [])
  return need.some((code) => have.has(code))
}

export function filterMenus<T extends Gated & { items?: T[] }>(
  menus: T[] | undefined,
  gate?: AccessGate | null,
): T[] {
  const out: T[] = []
  for (const menu of menus || []) {
    if (menu.items?.length) {
      const items = filterMenus(menu.items, gate)
      if (!items.length || !accessAllows(menu.access, gate)) continue
      out.push({ ...menu, items })
      continue
    }
    if (accessAllows(menu.access, gate)) out.push(menu)
  }
  return out
}

export function filterClicks<T extends Gated>(
  clicks: T[] | undefined,
  gate?: AccessGate | null,
): T[] | undefined {
  if (!clicks) return clicks
  return clicks.filter((click) => accessAllows(click.access, gate))
}

export function filterClickMap<T extends Gated>(
  clicks: Record<string, T> | undefined,
  gate?: AccessGate | null,
): Record<string, T> | undefined {
  if (!clicks) return clicks
  const out: Record<string, T> = {}
  for (const [key, click] of Object.entries(clicks)) {
    if (accessAllows(click?.access, gate)) out[key] = click
  }
  return out
}
