import type { SchemaField } from './record'
import { displayFieldValue, type ReferDict } from './fieldMeta'

function stamp() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`
}

export function safeExportBasename(title: string): string {
  const base = String(title || '导出')
    .replace(/[\\/:*?"<>|]+/g, '_')
    .replace(/\s+/g, '')
    .trim()
  return base || '导出'
}

function csvEscape(v: string): string {
  if (/[",\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`
  return v
}

/** 浏览器下载 CSV（无 xlsx 依赖；后续可换 Excel） */
export async function exportRows(opts: {
  title: string
  fields: SchemaField[]
  rows: Record<string, unknown>[]
  refers?: ReferDict
}): Promise<boolean> {
  const cols = opts.fields.filter((f) => f.shown !== false && f.field)
  const header = cols.map((f) => f.label || f.field)
  const lines = [
    header.map(csvEscape).join(','),
    ...opts.rows.map((row) =>
      cols
        .map((f) => csvEscape(displayFieldValue(row, f, { refers: opts.refers })))
        .join(','),
    ),
  ]
  const bom = '\uFEFF'
  const blob = new Blob([bom + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeExportBasename(opts.title)}-${stamp()}.csv`
  a.click()
  URL.revokeObjectURL(url)
  return true
}
