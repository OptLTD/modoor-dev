import { shallowRef, type Component } from 'vue'

/** 每个模块在系统托盘只挂一个组件。再次登记会替换，避免热更新叠一层。 */
const widgets = new Map<string, Component>()
const revision = shallowRef(0)

export function registerSysTrayWidget(moduleId: string, widget: Component) {
  const id = String(moduleId || '').trim()
  if (!id || !widget) return
  widgets.set(id, widget)
  revision.value += 1
}

export function resolveSysTrayWidget(moduleId: string): Component | undefined {
  revision.value
  return widgets.get(String(moduleId || '').trim())
}
