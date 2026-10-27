import type { SchemaRequest, SchemaTable } from '@modoor/hooks'

export type SheetRow = Record<string, string>

/** jspreadsheet worksheet 实例 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type SheetWorksheet = any

export type SchemaSheetProps = {
  table: SchemaTable
  request?: SchemaRequest
  /** modify=只改已有；import=只建新；默认 modify */
  mode?: 'modify' | 'import'
  /** 高度随行数增高，外层不再钉死 */
  autoHeight?: boolean
  /** 可见列（uukey 顺序）；空则跟 schema shown */
  fields?: string[]
}

export type RecalcPending = { row: number; col: number; triggerUukey: string }
