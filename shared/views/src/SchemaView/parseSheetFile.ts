/** Excel workbook → header row plus string rows. The first sheet with content is used. */

export type SheetGrid = { headers: string[]; rows: string[][] }

const EXCEL_EXTS = new Set(['xls', 'xlsx', 'xlsm', 'xlsb'])

export function sheetFileKind(name: string, mime = ''): 'csv' | 'excel' | 'other' {
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : ''
  const type = mime.toLowerCase()
  if (ext === 'csv' || type === 'text/csv' || type === 'application/csv') return 'csv'
  if (
    EXCEL_EXTS.has(ext) ||
    type === 'application/vnd.ms-excel' ||
    type.includes('spreadsheetml') ||
    type.includes('spreadsheet')
  ) {
    return 'excel'
  }
  return 'other'
}

/** Use the text Excel shows. Date cells become YYYY-MM-DD so timezones do not shift the day. */
function cellToString(value: unknown): string {
  const text = value == null ? '' : String(value).trim()
  if (!text) return ''
  // 兼容 Excel 美式：2026/10/28 5:26 PM、斜杠日期、未补零小时
  const match = text.match(
    /^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?)?$/,
  )
  if (!match) return text
  const ymd = `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`
  if (!match[4]) return ymd
  let hour = Number(match[4])
  const ap = (match[7] || '').toUpperCase()
  if (ap === 'PM' && hour < 12) hour += 12
  if (ap === 'AM' && hour === 12) hour = 0
  const hh = String(hour).padStart(2, '0')
  const mm = match[5]
  const ss = (match[6] || '00').padStart(2, '0')
  return `${ymd} ${hh}:${mm}:${ss}`
}

export async function parseExcelGrid(buf: ArrayBuffer): Promise<SheetGrid> {
  const XLSX = await import('xlsx')
  const book = XLSX.read(buf, { type: 'array' })
  for (const name of book.SheetNames) {
    const sheet = book.Sheets[name]
    if (!sheet) continue
    const grid = gridFromSheet(XLSX, sheet)
    if (grid.headers.some((cell) => cell) || grid.rows.length) return grid
  }
  return { headers: [], rows: [] }
}

function gridFromSheet(
  XLSX: typeof import('xlsx'),
  sheet: import('xlsx').WorkSheet,
): SheetGrid {
  const aoa = XLSX.utils.sheet_to_json(sheet, {
    header: 1,
    defval: '',
    raw: false,
  }) as unknown[][]
  if (!aoa.length) return { headers: [], rows: [] }
  const headers = (aoa[0] ?? []).map((cell) => cellToString(cell))
  const width = headers.length
  const rows: string[][] = []
  for (let i = 1; i < aoa.length; i++) {
    const line = (aoa[i] ?? []).map((cell) => cellToString(cell))
    if (line.every((cell) => !cell)) continue
    while (line.length < width) line.push('')
    rows.push(width ? line.slice(0, width) : line)
  }
  return { headers, rows }
}
