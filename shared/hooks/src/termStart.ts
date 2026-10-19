import { ref } from 'vue'

/** 财务期间切日。26 表示上月 26 日至本月 25 日。未读到设置时用 26。 */
export const DEFAULT_TERM_START = 26

export const termStart = ref(DEFAULT_TERM_START)

export function getTermStart(): number {
  const n = termStart.value
  return Number.isInteger(n) && n >= 2 && n <= 28 ? n : DEFAULT_TERM_START
}

export function setTermStart(raw: unknown) {
  const n = Number(raw)
  termStart.value = Number.isInteger(n) && n >= 2 && n <= 28 ? n : DEFAULT_TERM_START
}
