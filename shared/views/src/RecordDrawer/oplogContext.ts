import type { InjectionKey } from 'vue'

export type RecordDrawerOplogApi = {
  setTarget: (model: string, uukey: string) => void
  clearTarget: () => void
}

export const RECORD_DRAWER_OPLOG_KEY: InjectionKey<RecordDrawerOplogApi> =
  Symbol('recordDrawerOplog')
