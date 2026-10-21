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
  const match = text.match(
    /^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?$/,
  )
  if (!match) return text
  const ymd = `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`
  return match[4] ? `${ymd} ${match[4]}` : ymd
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
