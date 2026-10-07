import type { Component } from 'vue'

/** Module webui registers drawer body components keyed by model uukey. */
const registry = new Map<string, Component>()

export function registerRecordView(model: string, view: Component) {
  const key = String(model || '').trim()
  if (!key || !view) return
  registry.set(key, view)
}

export function registerRecordViews(views: Record<string, Component>) {
  for (const [model, view] of Object.entries(views)) {
    registerRecordView(model, view)
  }
}

export function resolveRecordView(model: string): Component | undefined {
  return registry.get(String(model || '').trim())
}

export function clearRecordViews() {
  registry.clear()
}
