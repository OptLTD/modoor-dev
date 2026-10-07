import type { RecordGateway, SchemaField } from '@modoor/hooks'
import {
  ACTION_WIDTH_KEY,
  fieldKey,
  modFromModel,
  viewWidths,
} from '@modoor/hooks'
import { defaultColWidth } from './fieldUtils'

export async function loadColWidths(
  model: string,
  using: string,
  _fields: SchemaField[],
  colWidths: Record<string, number>,
  gateway: RecordGateway,
) {
  for (const k of Object.keys(colWidths)) delete colWidths[k]
  const mod = modFromModel(model)
  if (!mod) return
  try {
    const layout = await gateway.fetchTableLayout(mod)
    const server = viewWidths(layout, model, using || 'default')
    for (const [fk, n] of Object.entries(server)) {
      if (fk === ACTION_WIDTH_KEY) continue
      if (!Number.isFinite(n) || n < 40) continue
      colWidths[fk] = n
    }
  } catch {
    /* ignore */
  }
}

export function saveColWidth(
  model: string,
  using: string,
  fk: string,
  width: number,
  colWidths: Record<string, number>,
  gateway: RecordGateway,
) {
  const w = Math.max(40, Math.round(width))
  colWidths[fk] = w
  gateway.patchTableWidth(model, using || 'default', fk, w)
}

export function resolveColWidth(f: SchemaField, colWidths: Record<string, number>) {
  const fk = fieldKey(f)
  if (colWidths[fk]) return colWidths[fk]
  return defaultColWidth(f)
}
