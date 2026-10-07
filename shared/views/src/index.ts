/**
 * @modoor/views — screens that call the record API, then render @modoor/widget controls.
 *   import { SchemaView } from '@modoor/views/SchemaView'
 */
export { SchemaView } from './SchemaView'
export type { SchemaViewTab, SchemaViewHandlers } from './SchemaView'
export { default as RecordDialog, useRecordDialog } from './RecordDialog'
export { default as RecordDrawer } from './RecordDrawer'
export {
  RecordFlatDetail,
  RecordOpLog,
  registerRecordView,
  registerRecordViews,
  resolveRecordView,
  clearRecordViews,
} from './RecordDrawer'
export { default as RecordEntity, defineRecordEntityView } from './RecordEntity'
export { default as TableDrawer } from './TableDrawer'
export { ChartView } from './ChartView'
export type { ChartBoard, ChartCard, ChartLayout, ChartsFile } from './ChartView'
export { default as ShellFrame, registerSysTrayWidget } from './ShellFrame'
