/** 轻量对话框：浏览器原生确认；toast 用固定浮层 */

export async function appAlert(message: string, _title = '提示'): Promise<void> {
  window.alert(message)
}

export async function appConfirm(
  message: string,
  _title = '确认',
  _opts?: { confirmText?: string; cancelText?: string },
): Promise<boolean> {
  return window.confirm(message)
}

const TOAST_STYLE = `
.md-toast-host {
  position: fixed;
  left: 50%;
  top: 1.25rem;
  transform: translateX(-50%);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  pointer-events: none;
}
.md-toast {
  max-width: min(92vw, 28rem);
  padding: 10px 18px;
  border-radius: 999px;
  border: 1px solid var(--line, #e2e6eb);
  background: color-mix(in srgb, var(--panel, #ffffff) 92%, #1c1917);
  color: var(--ink, #1c1914);
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.4;
  box-shadow: 0 10px 28px #1c191724;
  animation: md-toast-in 0.18s ease-out;
}
.md-toast.error {
  border-color: color-mix(in srgb, var(--danger, #a33b2b) 45%, var(--line, #e2e6eb));
  background: #fef2f2;
  color: var(--danger, #a33b2b);
}
@keyframes md-toast-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
`

let host: HTMLElement | null = null
let hideTimer = 0

function ensureHost(): HTMLElement {
  if (host && document.body.contains(host)) return host
  if (!document.getElementById('md-toast-style')) {
    const style = document.createElement('style')
    style.id = 'md-toast-style'
    style.textContent = TOAST_STYLE
    document.head.appendChild(style)
  }
  host = document.createElement('div')
  host.className = 'md-toast-host'
  host.setAttribute('aria-live', 'polite')
  document.body.appendChild(host)
  return host
}

export function appToast(message: string, kind: 'info' | 'error' = 'info'): void {
  const text = (message || '').trim()
  if (!text) return
  const root = ensureHost()
  root.replaceChildren()
  const el = document.createElement('div')
  el.className = kind === 'error' ? 'md-toast error' : 'md-toast'
  el.setAttribute('role', 'status')
  el.textContent = text
  root.appendChild(el)
  window.clearTimeout(hideTimer)
  hideTimer = window.setTimeout(() => {
    el.remove()
  }, kind === 'error' ? 4200 : 1800)
}
