import { ref, watch } from 'vue'
import { listNav, uploadAsset, type ModelItem, type TagItem } from '../api/doc'

export type ViewMode = 'list' | 'icon' | 'split'

export type DocFilter =
  | { kind: 'all' }
  | { kind: 'model'; model: string }
  | { kind: 'model-empty' }
  | { kind: 'tag'; tag: string }
  | { kind: 'tag-empty' }

const VIEW_KEY = 'doc.folder.view'

function readView(): ViewMode {
  try {
    const v = localStorage.getItem(VIEW_KEY)
    if (v === 'list' || v === 'icon' || v === 'split') return v
  } catch {
    /* ignore */
  }
  return 'list'
}

export const viewMode = ref<ViewMode>(readView())
export const docFilter = ref<DocFilter>({ kind: 'all' })
export const docQuery = ref('')
export const models = ref<ModelItem[]>([])
export const tags = ref<TagItem[]>([])
export const modelEmpty = ref(0)
export const tagEmpty = ref(0)
export const uploading = ref(false)
export const navError = ref('')
/** 上传或侧栏数据变化后加一，列表页据此重载。 */
export const libraryEpoch = ref(0)

watch(viewMode, (v) => {
  try {
    localStorage.setItem(VIEW_KEY, v)
  } catch {
    /* ignore */
  }
})

export function modelLabel(model: string) {
  const key = model.trim()
  if (!key) return ''
  const hit = models.value.find((item) => item.model === key)
  return hit?.title || key
}

export function chooseAll() {
  docFilter.value = { kind: 'all' }
}

export function chooseModel(model: string) {
  const current = docFilter.value
  docFilter.value =
    current.kind === 'model' && current.model === model
      ? { kind: 'all' }
      : { kind: 'model', model }
}

export function chooseModelEmpty() {
  docFilter.value = docFilter.value.kind === 'model-empty' ? { kind: 'all' } : { kind: 'model-empty' }
}

export function chooseTag(tag: string) {
  const current = docFilter.value
  docFilter.value =
    current.kind === 'tag' && current.tag === tag ? { kind: 'all' } : { kind: 'tag', tag }
}

export function chooseTagEmpty() {
  docFilter.value = docFilter.value.kind === 'tag-empty' ? { kind: 'all' } : { kind: 'tag-empty' }
}

export async function refreshNav() {
  navError.value = ''
  try {
    const nav = await listNav()
    models.value = nav.models || []
    tags.value = nav.tags || []
    modelEmpty.value = nav.model_empty || 0
    tagEmpty.value = nav.tag_empty || 0
  } catch (e) {
    navError.value = e instanceof Error ? e.message : String(e)
  }
}

export async function uploadDocFiles(files: File[]): Promise<string> {
  const list = files.filter(Boolean)
  if (!list.length) return ''
  uploading.value = true
  navError.value = ''
  try {
    const filter = docFilter.value
    const tagHint = filter.kind === 'tag' ? [filter.tag] : undefined
    const modelHint = filter.kind === 'model' ? filter.model : undefined
    let lastId = ''
    for (const file of list) {
      const res = await uploadAsset(file, { tags: tagHint, model: modelHint })
      lastId = res.asset?.id || ''
    }
    await refreshNav()
    libraryEpoch.value += 1
    return lastId
  } catch (e) {
    navError.value = e instanceof Error ? e.message : String(e)
    return ''
  } finally {
    uploading.value = false
  }
}
