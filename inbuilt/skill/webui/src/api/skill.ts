import { get, post } from '@modoor/hooks'

export type SkillItem = {
  id: string
  record_id?: string
  source: 'module' | 'custom' | 'override'
  overridden?: boolean
  readonly: boolean
  disabled?: boolean
  module: string
  skill_key: string
  title: string
  summary?: string
  when_to_use?: string
  tools?: unknown[]
  confirmations?: unknown[]
  boundaries?: string
  content?: string
  markdown?: string
  updated_at?: string | null
  uri?: string
}

export async function listSkills(params?: { source?: string; q?: string }) {
  const qs = new URLSearchParams()
  if (params?.source) qs.set('source', params.source)
  if (params?.q) qs.set('q', params.q)
  const suffix = qs.toString() ? `?${qs}` : ''
  return get<{ items: SkillItem[]; count: number }>(`/api/skill/skills${suffix}`)
}

export async function getSkill(skillId: string) {
  return get<{ skill: SkillItem }>(
    `/api/skill/skills/${encodeURIComponent(skillId)}`,
  )
}

export async function saveSkill(body: {
  skill_id?: string
  module?: string
  skill_key?: string
  title: string
  summary?: string
  when_to_use?: string
  content?: string
  tools?: unknown[]
  confirmations?: unknown[]
  boundaries?: string
  record_id?: string
}) {
  return post<{ ok: boolean; skill: SkillItem }>('/api/skill/skills', body)
}

export async function setSkillDisabled(skillId: string, disabled: boolean) {
  return post<{ ok: boolean; skill: SkillItem }>(
    `/api/skill/skills/${encodeURIComponent(skillId)}/disabled`,
    { disabled },
  )
}

export async function deleteSkill(skillId: string) {
  const res = await fetch(`/api/skill/skills/${encodeURIComponent(skillId)}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
