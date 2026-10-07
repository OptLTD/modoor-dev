import { provide } from 'vue'
import {
  allocSerials,
  autofillBatch,
  autofillRecord,
  deleteRecords,
  fetchInputSchema,
  fetchTableColumns,
  fetchTableLayout,
  loadDropdownRefers,
  patchTableWidth,
  saveTableColumns,
  recordGatewayKey,
  searchRecords,
  upsertRecords,
  uploadAsset,
  fetchAsset,
  type RecordGateway,
} from '@modoor/hooks'

const gateway: RecordGateway = {
  searchRecords,
  deleteRecords,
  fetchTableColumns,
  fetchTableLayout,
  patchTableWidth,
  saveTableColumns,
  upsertRecords,
  fetchInputSchema,
  loadDropdownRefers,
  autofillRecord,
  autofillBatch,
  allocSerials,
  uploadAsset,
  fetchAsset,
}

/** 在外壳 setup 里调用，子组件里的列表和表格通过 inject 使用。 */
export function provideRecordGateway() {
  provide(recordGatewayKey, gateway)
}
