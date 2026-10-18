/** 浏览器标题：页面名称-租户名称。内容页可以临时盖住菜单名。 */

let shellPage = ''
let tenantName = ''
let contentPage: string | null = null

function paint() {
  const page = (contentPage ?? shellPage).trim()
  const tenant = tenantName.trim()
  if (page && tenant) document.title = `${page}-${tenant}`
  else document.title = page || tenant || 'Modoor'
}

export function setShellDocumentTitle(pageName: string, tenant: string) {
  shellPage = String(pageName || '').trim()
  tenantName = String(tenant || '').trim()
  paint()
}

/** 传入当前内容标题；离开页面时传 null，恢复菜单名。 */
export function setContentDocumentTitle(title: string | null) {
  const next = String(title || '').trim()
  contentPage = next || null
  paint()
}
