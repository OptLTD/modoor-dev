export type FlowTask = {
  id: string
  instance_id: string
  title: string
  status: string
  level: number
  comment?: string
}

export type FlowInstance = {
  id: string
  definition_key: string
  status: string
  current_node: string
  context: Record<string, unknown>
}

export type FlowDefinition = {
  id: string
  key: string
  title: string
  status: string
  version: number
  graph: Record<string, unknown>
  trigger: Record<string, unknown>
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: 'include',
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers || {}),
    },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data?.detail || data?.message || res.statusText)
  return data as T
}

export function listTasks(status = 'pending') {
  return json<{ items: FlowTask[]; count: number }>(`/api/flow/tasks?status=${encodeURIComponent(status)}`)
}

export function decideTask(taskId: string, decision: string, comment = '') {
  return json<{ ok: boolean; task: FlowTask }>(`/api/flow/tasks/${taskId}/decide`, {
    method: 'POST',
    body: JSON.stringify({ decision, comment }),
  })
}

export function listInstances(opts?: { status?: string; definition_key?: string }) {
  const q = new URLSearchParams()
  if (opts?.status) q.set('status', opts.status)
  if (opts?.definition_key) q.set('definition_key', opts.definition_key)
  const qs = q.toString()
  return json<{ items: FlowInstance[]; count: number }>(`/api/flow/instances${qs ? `?${qs}` : ''}`)
}

export function getInstance(id: string) {
  return json<{ instance: FlowInstance; logs: unknown[]; tasks: FlowTask[] }>(
    `/api/flow/instances/${id}`,
  )
}

export function listDefinitions() {
  return json<{ items: FlowDefinition[]; count: number }>('/api/flow/definitions')
}

export function upsertDefinition(body: Partial<FlowDefinition> & { key: string; definition_id?: string }) {
  return json<{ ok: boolean; definition: FlowDefinition }>('/api/flow/definitions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function listSchedules() {
  return json<{ items: Array<Record<string, unknown>>; count: number }>('/api/flow/schedules')
}

export function upsertSchedule(body: Record<string, unknown>) {
  return json<{ ok: boolean; schedule: Record<string, unknown> }>('/api/flow/schedules', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
