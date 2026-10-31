/**
 * jspreadsheet / jSuites 右键菜单与内置文案：按系统 locale 套词典。
 * translate() 以英文原句为 key，不能直接用 resources/lang/zh_CN.json 的 camelCase。
 */
import jspreadsheet from 'jspreadsheet-ce'
import { getLocale, subscribeLocale, type LocaleCode } from '@modoor/hooks'

/** CE 运行时有 setDictionary，官方类型未声明 */
type JspreadsheetWithDict = typeof jspreadsheet & {
  setDictionary: (dict: Record<string, string>) => void
}

/** 与 jSuites.translate("…") 调用字符串一一对应 */
const ZH_SHEET_DICT: Record<string, string> = {
  About: '关于',
  'Are you sure to delete the selected columns?': '确定删除选定列?',
  'Are you sure to delete the selected rows?': '确定删除选定行?',
  'Clear comments': '删除批注',
  'Column name': '列标题',
  Comments: '批注',
  Copy: '复制...',
  'Delete selected columns': '删除选定列',
  'Delete selected rows': '删除选定行',
  'Insert a new column after': '在此后插入列',
  'Insert a new column before': '在此前插入列',
  'Insert a new row after': '在此后插入行',
  'Insert a new row before': '在此前插入行',
  'Merge the selected cells': '合并选定单元格',
  'No cells selected': '未选定单元格',
  'No records found': '未找到',
  'Order ascending': '升序',
  'Order descending': '降序',
  Paste: '粘贴...',
  'Rename this column': '重命名列',
  'Save as': '保存为...',
  Search: '搜索',
  'Show ': '显示 ',
  'Showing page {0} of {1} entries': '显示 {1} 条中的第 {0} 条',
  'The merged cells will retain the value of the top-left cell only. Are you sure?':
    '合并后仅保留左上角单元格的值，确认操作？',
  'This action will clear your search results. Are you sure?':
    '这一操作会清空搜索结果，确认操作？',
  'This action will destroy any existing merged cells. Are you sure?':
    '这一操作会破坏所有现存的合并单元格，确认操作？',
  entries: ' 条目',
  // jsuites 日历 / 通用
  Done: '完成',
  Reset: '重置',
  Update: '更新',
  Menu: '菜单',
  close: '关闭',
  'Date outside the valid range': '日期超出有效范围',
  'Add A New Option': '添加新选项',
  'This extension is not allowed': '不允许此扩展名',
  'You reach the limit number of entries': '已达到条目上限',
}

const EN_RESET: Record<string, string> = Object.fromEntries(
  Object.keys(ZH_SHEET_DICT).map((k) => [k, k]),
)

let applied: LocaleCode | null = null
let subscribed = false

export function applySheetLocale(locale: string = getLocale()): void {
  const next = locale.startsWith('zh') ? ('zh-CN' as const) : ('en-US' as const)
  if (applied === next) return
  ;(jspreadsheet as JspreadsheetWithDict).setDictionary(
    next === 'zh-CN' ? ZH_SHEET_DICT : EN_RESET,
  )
  applied = next
}

/** 模块加载时挂上 locale 监听，切语言后新建的 sheet 右键即生效 */
export function ensureSheetLocaleSync(): void {
  applySheetLocale()
  if (subscribed) return
  subscribed = true
  subscribeLocale(() => {
    applied = null
    applySheetLocale()
  })
}
