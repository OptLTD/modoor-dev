import { inject, type InjectionKey } from 'vue'
import type { loadDropdownRefers } from './fieldMeta'
import type {
  allocSerials,
  autofillBatch,
  autofillRecord,
  deleteRecords,
  fetchInputSchema,
  searchRecords,
  upsertRecords,
} from './record'
import type { fetchTableColumns, saveTableColumns } from './tableColumns'
import type { fetchTableLayout, patchTableWidth } from './tableLayout'
import type { fetchAsset, uploadAsset } from './upload'

/** 列表、表格、表单用到的记录接口。实现由 views 注入，widget 不直接发请求。 */
export type RecordGateway = {
  searchRecords: typeof searchRecords
  deleteRecords: typeof deleteRecords
  fetchTableLayout: typeof fetchTableLayout
  patchTableWidth: typeof patchTableWidth
  fetchTableColumns: typeof fetchTableColumns
  saveTableColumns: typeof saveTableColumns
  upsertRecords: typeof upsertRecords
  fetchInputSchema: typeof fetchInputSchema
  loadDropdownRefers: typeof loadDropdownRefers
  autofillRecord: typeof autofillRecord
  autofillBatch: typeof autofillBatch
  allocSerials: typeof allocSerials
  uploadAsset: typeof uploadAsset
  fetchAsset: typeof fetchAsset
}

export const recordGatewayKey: InjectionKey<RecordGateway> = Symbol('recordGateway')

export function useRecordGateway(): RecordGateway {
  const gateway = inject(recordGatewayKey)
  if (!gateway) {
    throw new Error('Record gateway is missing. Provide it from the view shell.')
  }
  return gateway
}
