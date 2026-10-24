import { readFileSync } from 'node:fs'

/** 大依赖单独成包。列表页只在用到表格或 Excel 时再拉这些文件。 */
export function manualChunks(id) {
  const path = String(id || '').replaceAll('\\', '/')
  if (path.includes('/jsuites/')) return 'jsuites'
  if (path.includes('/jspreadsheet-ce/')) return 'jspreadsheet'
  if (path.includes('/xlsx/')) return 'xlsx'
  if (path.includes('/exceljs/')) return 'exceljs'
}

/** 产物名 → node_modules 里的包目录。 */
const PACKAGES = {
  xlsx: 'xlsx',
  exceljs: 'exceljs',
  jsuites: 'jsuites',
  jspreadsheet: 'jspreadsheet-ce',
}

function versionInFile(file, dirName) {
  const normalized = String(file || '').replaceAll('\\', '/')
  const marker = `/${dirName}/`
  const at = normalized.lastIndexOf(marker)
  if (at < 0) return ''
  try {
    const pkg = JSON.parse(readFileSync(`${normalized.slice(0, at)}${marker}package.json`, 'utf8'))
    return pkg.version ? String(pkg.version) : ''
  } catch {
    return ''
  }
}

function packageVersion(chunk, dirName) {
  for (const id of chunk.moduleIds || []) {
    const version = versionInFile(id, dirName)
    if (version) return version
  }
  return ''
}

/** 这些库用包版本做文件名。应用重新发布时地址不变，浏览器继续用缓存。 */
export function chunkFileNames(chunk) {
  const name = String(chunk.name || '')
  const dirName = PACKAGES[name]
  if (dirName) {
    const version = packageVersion(chunk, dirName)
    if (version) return `assets/${name}-${version}.js`
    return `assets/${name}.js`
  }
  return 'assets/[name]-[hash].js'
}

/** 样式资源只有文件名，版本从当前模块的 node_modules 读。 */
const CSS_PACKAGES = {
  'jspreadsheet.css': ['jspreadsheet', 'jspreadsheet-ce'],
  'jsuites.css': ['jsuites', 'jsuites'],
}

function installedVersion(dirName) {
  try {
    const pkg = JSON.parse(readFileSync(`${process.cwd()}/node_modules/${dirName}/package.json`, 'utf8'))
    return pkg.version ? String(pkg.version) : ''
  } catch {
    return ''
  }
}

export function assetFileNames(asset) {
  const base = String(asset.name || (asset.names || [])[0] || '')
  const mapped = CSS_PACKAGES[base]
  if (mapped) {
    const [name, dirName] = mapped
    const version = installedVersion(dirName)
    if (version) return `assets/${name}-${version}.css`
    return `assets/${name}.css`
  }
  const files = [...(asset.originalFileNames || []), ...(asset.names || []), asset.name || '']
  for (const [name, dirName] of Object.entries(PACKAGES)) {
    const hit = files.find((file) => String(file).replaceAll('\\', '/').includes(`/${dirName}/`))
    if (!hit) continue
    const version = versionInFile(hit, dirName)
    const ext = String(hit).match(/\.[^.]+$/)?.[0] || '[extname]'
    if (version) return `assets/${name}-${version}${ext}`
    return `assets/${name}${ext}`
  }
  return 'assets/[name]-[hash][extname]'
}
