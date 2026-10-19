/** jspreadsheet-ce 用 eval 判断公式里的单元格名，构建时不必当成本仓库的问题。 */
export function rollupOnwarn(warning, warn) {
  const id = String(warning.id || '')
  if (warning.code === 'EVAL' && id.includes('jspreadsheet-ce')) return
  warn(warning)
}
