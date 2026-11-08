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

function columnWidth(label: string): number {
  let width = 8
  for (const ch of label) width += ch.charCodeAt(0) > 255 ? 2 : 1
  return Math.min(40, width)
}

/** 浏览器下载 xlsx。列表和 Sheet 导出共用，按当前表头顺序和显示值生成。 */
export async function exportRows(opts: {
  title: string
  fields: SchemaField[]
  rows: Record<string, unknown>[]
  refers?: ReferDict
}): Promise<boolean> {
  // 调用方传入的就是当前表头（含列设置后的顺序和显隐）。schema 的 shown 只是默认列，不能再滤一次。
  const cols = opts.fields.filter((f) => f.field)
  const header = cols.map((f) => f.label || f.field)
  const body = opts.rows.map((row) =>
    cols.map((f) => displayFieldValue(row, f, { refers: opts.refers })),
  )

  const XLSX = await import('xlsx')
  const sheet = XLSX.utils.aoa_to_sheet([header, ...body])
  sheet['!cols'] = cols.map((f) => ({ wch: columnWidth(String(f.label || f.field)) }))
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, sheet, '数据')
  const data = XLSX.write(book, { bookType: 'xlsx', type: 'array' }) as ArrayBuffer

  const blob = new Blob([data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeExportBasename(opts.title)}-${stamp()}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
  return true
}
