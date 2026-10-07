<template>
  <section class="roles-page">
    <p v-if="error" class="error">{{ error }}</p>

    <div class="roles-split">
      <!-- 左侧：角色列表 -->
      <aside class="roles-left panel">
        <header class="pane-head">
          <h1>{{ t('base.roles') }}</h1>
          <button type="button" class="btn primary" @click="openCreate">
            {{ t('base.create') }}
          </button>
        </header>

        <ul class="role-list">
          <li
            v-for="r in roles"
            :key="r.id"
            class="role-item"
            :class="{ active: selectedId === r.id }"
            @click="selectRole(r.id)"
          >
            <div class="role-item-main">
              <strong>{{ r.name }}</strong>
              <code>{{ r.code }}</code>
            </div>
            <span class="ability-count muted">
              {{ t('base.nodes', { n: (roleNodes[r.id] || []).length }) }}
            </span>
          </li>
          <li v-if="!roles.length" class="muted empty">{{ t('base.noRoles') }}</li>
        </ul>
      </aside>

      <!-- 右侧：权限 + 分配 -->
      <main class="roles-right panel">
        <template v-if="selected">
          <header class="pane-head">
            <div>
              <h1>{{ selected.name }}</h1>
            </div>
            <div class="head-actions">
              <button type="button" class="btn" :disabled="saving || !flatVisible.length" @click="toggleSelectVisible">
                {{ allVisibleSelected ? t('base.clear') : t('base.selectAllVisible') }}
              </button>
              <button
                type="button"
                class="btn primary"
                :disabled="saving || !dirty"
                @click="onSaveAbilities"
              >
                {{ saving ? t('base.saving') : t('base.saveAbilities') }}
              </button>
              <Dropdown align="end" :label="t('base.more')">
                <button type="button" class="dropdown-item" role="menuitem" @click="onMoreAssign">
                  {{ t('base.assignUsers') }}
                </button>
                <button
                  type="button"
                  class="dropdown-item danger"
                  role="menuitem"
                  @click="onMoreDelete"
                >
                  {{ t('base.delete') }}
                </button>
              </Dropdown>
            </div>
          </header>

          <div class="perm-toolbar">
            <input
              v-model="permKeyword"
              type="search"
              class="perm-search"
              :placeholder="t('base.filterAbilities')"
            />
            <span class="muted">{{ t('base.selectedCount', { n: draftAbilities.length, total: flatCatalog.length }) }}</span>
          </div>

          <div class="perm-groups">
            <section
              v-for="g in filteredCatalog"
              :key="g.module_id"
              class="perm-group"
            >
              <header class="group-head">
                <label class="group-check">
                  <input
                    type="checkbox"
                    :checked="moduleAllChecked(g)"
                    @change="toggleModule(g, ($event.target as HTMLInputElement).checked)"
                  />
                  <strong>{{ moduleLabel(g) }}</strong>
                  <span class="muted">{{ g.module_id }}</span>
                </label>
              </header>
              <div class="ability-grid">
                <label
                  v-for="a in g.abilities"
                  :key="a"
                  class="ability-item"
                >
                  <input
                    type="checkbox"
                    :checked="draftSet.has(a)"
                    @change="toggleAbility(a, ($event.target as HTMLInputElement).checked)"
                  />
                  <span class="ability-name">{{ abilityLabel(g, a) }}</span>
                </label>
              </div>
            </section>
            <p v-if="!filteredCatalog.length" class="muted empty">{{ t('base.noAbilities') }}</p>
          </div>
        </template>

        <div v-else class="empty-right muted">
          {{ t('base.pickRole') }}
        </div>
      </main>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <header class="modal-head">
          <strong>{{ t('base.createRole') }}</strong>
          <button type="button" class="link" @click="closeCreate">{{ t('widget.close') }}</button>
        </header>
        <form class="form" @submit.prevent="onCreate">
          <label>
            {{ t('base.roleName') }}
            <input v-model="form.name" required autocomplete="off" />
          </label>
          <label>
            {{ t('base.roleDescription') }}
            <input v-model="form.description" autocomplete="off" />
          </label>
          <p v-if="createError" class="error">{{ createError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn" @click="closeCreate">{{ t('widget.cancel') }}</button>
            <button type="submit" class="btn primary" :disabled="creating">
              {{ creating ? t('widget.saving') : t('widget.formCreate') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showAssign" class="modal-mask" @click.self="closeAssign">
      <div class="modal assign-modal">
        <header class="modal-head">
          <strong>{{ t('base.assignUsers') }}</strong>
          <button type="button" class="link" @click="closeAssign">{{ t('widget.close') }}</button>
        </header>
        <form class="form assign-form" @submit.prevent="onAssign">
          <div class="perm-toolbar">
            <input
              v-model="assignKeyword"
              type="search"
              class="perm-search"
              :placeholder="t('base.filterUsers')"
            />
            <span class="muted">
              {{ t('base.selectedCount', { n: pickedUserIds.length, total: filteredAssignUsers.length }) }}
            </span>
          </div>
          <div class="assign-user-grid">
            <label
              v-for="u in filteredAssignUsers"
              :key="u.id"
              class="assign-user-item"
            >
              <input
                type="checkbox"
                :checked="pickedUserSet.has(u.id)"
                @change="togglePickedUser(u.id, ($event.target as HTMLInputElement).checked)"
              />
              <span class="assign-user-text">
                <span class="assign-user-name">{{ u.realname || u.username }}</span>
                <code v-if="u.realname" class="muted">{{ u.username }}</code>
              </span>
            </label>
          </div>
          <p v-if="!users.length" class="muted">{{ t('base.noMatchingUsers') }}</p>
          <p v-else-if="!filteredAssignUsers.length" class="muted">{{ t('base.noMatchingUsers') }}</p>
          <p v-if="assignError" class="error">{{ assignError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn" @click="closeAssign">{{ t('widget.cancel') }}</button>
            <button
              type="submit"
              class="btn primary"
              :disabled="assigning || !assignDirty"
            >
              {{ assigning ? t('widget.saving') : t('widget.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Dropdown } from '@modoor/widget'
import {
  useI18n,
  localizedAppLabel,
  localizedEntityLabel,
  type ManifestI18n,
} from '@modoor/hooks'
import {
  assignRole,
  createRole,
  deleteRole,
  revokeRole,
  rolesBundle,
  setRoleNodes,
  type User,
} from '../api/base'

type Role = {
  id: string
  code: string
  name: string
  description?: string | null
}

type AbilityGroup = {
  module_id: string
  label: string
  i18n?: ManifestI18n
  abilities: string[]
}

const { t, locale } = useI18n()
const error = ref('')
const roles = ref<Role[]>([])
const users = ref<User[]>([])
const assignments = ref<Record<string, { id: string; code: string }[]>>({})
const roleNodes = ref<Record<string, string[]>>({})
const catalog = ref<AbilityGroup[]>([])

const selectedId = ref('')
const draftAbilities = ref<string[]>([])
const savedSnapshot = ref('')
const saving = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const showAssign = ref(false)
const assigning = ref(false)
const assignError = ref('')
const permKeyword = ref('')
const assignKeyword = ref('')
const form = reactive({ name: '', description: '' })
const pickedUserIds = ref<number[]>([])

const selected = computed(() => roles.value.find((r) => r.id === selectedId.value) || null)
const draftSet = computed(() => new Set(draftAbilities.value))
const dirty = computed(() => JSON.stringify([...draftAbilities.value].sort()) !== savedSnapshot.value)
const flatCatalog = computed(() => catalog.value.flatMap((g) => g.abilities))
const flatVisible = computed(() => filteredCatalog.value.flatMap((g) => g.abilities))
const allVisibleSelected = computed(
  () => flatVisible.value.length > 0 && flatVisible.value.every((a) => draftSet.value.has(a)),
)

const holders = computed(() => {
  if (!selected.value) return []
  const rid = selected.value.id
  return users.value.filter((u) => (assignments.value[u.id] || []).some((r) => r.id === rid))
})

const holderIdSet = computed(() => new Set(holders.value.map((u) => u.id)))

const pickedUserSet = computed(() => new Set(pickedUserIds.value))

const assignDirty = computed(() => {
  const next = [...pickedUserIds.value].sort((a, b) => a - b)
  const prev = [...holderIdSet.value].sort((a, b) => a - b)
  return JSON.stringify(next) !== JSON.stringify(prev)
})

const filteredAssignUsers = computed(() => {
  const q = assignKeyword.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter((u) => {
    const name = (u.realname || '').toLowerCase()
    const user = (u.username || '').toLowerCase()
    return name.includes(q) || user.includes(q)
  })
})

const filteredCatalog = computed(() => {
  const q = permKeyword.value.trim().toLowerCase()
  if (!q) return catalog.value
  return catalog.value
    .map((g) => ({
      ...g,
      abilities: g.abilities.filter((a) => {
        const name = abilityLabel(g, a).toLowerCase()
        return (
          a.toLowerCase().includes(q) ||
          name.includes(q) ||
          g.module_id.toLowerCase().includes(q) ||
          moduleLabel(g).toLowerCase().includes(q)
        )
      }),
    }))
    .filter((g) => g.abilities.length)
})

function moduleLabel(g: AbilityGroup) {
  return localizedAppLabel({ label: g.label, i18n: g.i18n }, locale.value, g.label)
}

function abilityLabel(g: AbilityGroup, code: string) {
  return localizedEntityLabel(g.i18n, { id: code, label: code }, locale.value, code)
}

function selectRole(id: string) {
  selectedId.value = id
  const abs = [...(roleNodes.value[id] || [])].sort()
  draftAbilities.value = abs
  savedSnapshot.value = JSON.stringify(abs)
}

function toggleAbility(code: string, on: boolean) {
  const set = new Set(draftAbilities.value)
  if (on) set.add(code)
  else set.delete(code)
  draftAbilities.value = [...set].sort()
}

function moduleAllChecked(g: AbilityGroup) {
  return g.abilities.length > 0 && g.abilities.every((a) => draftSet.value.has(a))
}

function toggleModule(g: AbilityGroup, on: boolean) {
  const set = new Set(draftAbilities.value)
  for (const a of g.abilities) {
    if (on) set.add(a)
    else set.delete(a)
  }
  draftAbilities.value = [...set].sort()
}

function selectAllModule() {
  const set = new Set(draftAbilities.value)
  for (const g of filteredCatalog.value) {
    for (const a of g.abilities) set.add(a)
  }
  draftAbilities.value = [...set].sort()
}

function clearVisible() {
  const visible = new Set(flatVisible.value)
  draftAbilities.value = draftAbilities.value.filter((a) => !visible.has(a))
}

function toggleSelectVisible() {
  if (allVisibleSelected.value) clearVisible()
  else selectAllModule()
}

function onMoreAssign() {
  openAssign()
}

function onMoreDelete() {
  if (!selected.value) return
  void onDelete(selected.value.id, selected.value.code)
}

async function reload() {
  error.value = ''
  try {
    const res = await rolesBundle()
    roles.value = res.roles
    users.value = res.users
    assignments.value = res.assignments
    roleNodes.value = res.role_nodes || {}
    catalog.value = res.ability_catalog?.modules || []
    const keep = selectedId.value && roles.value.some((r) => r.id === selectedId.value)
    if (keep) selectRole(selectedId.value)
    else if (roles.value[0]) selectRole(roles.value[0].id)
    else {
      selectedId.value = ''
      draftAbilities.value = []
      savedSnapshot.value = '[]'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function openCreate() {
  form.name = form.description = ''
  createError.value = ''
  showCreate.value = true
}

function closeCreate() {
  if (creating.value) return
  showCreate.value = false
  createError.value = ''
}

async function onCreate() {
  creating.value = true
  createError.value = ''
  try {
    const created = await createRole({
      name: form.name,
      description: form.description || undefined,
    })
    form.name = form.description = ''
    showCreate.value = false
    await reload()
    if (created.role?.id) selectRole(created.role.id)
  } catch (e) {
    createError.value = e instanceof Error ? e.message : String(e)
  } finally {
    creating.value = false
  }
}

function openAssign() {
  if (!selected.value) return
  pickedUserIds.value = holders.value.map((u) => u.id)
  assignKeyword.value = ''
  assignError.value = ''
  showAssign.value = true
}

function closeAssign() {
  if (assigning.value) return
  showAssign.value = false
  assignError.value = ''
}

function togglePickedUser(id: number, on: boolean) {
  const set = new Set(pickedUserIds.value)
  if (on) set.add(id)
  else set.delete(id)
  pickedUserIds.value = [...set]
}

async function onAssign() {
  if (!selected.value || !assignDirty.value) return
  assigning.value = true
  assignError.value = ''
  try {
    const roleId = selected.value.id
    const next = pickedUserSet.value
    const prev = holderIdSet.value
    for (const userId of next) {
      if (!prev.has(userId)) await assignRole(userId, roleId)
    }
    for (const userId of prev) {
      if (!next.has(userId)) await revokeRole(userId, roleId)
    }
    showAssign.value = false
    await reload()
  } catch (e) {
    assignError.value = e instanceof Error ? e.message : String(e)
  } finally {
    assigning.value = false
  }
}

async function onDelete(id: string, code: string) {
  if (!confirm(`Delete role ${code}?`)) return
  try {
    await deleteRole(id)
    if (selectedId.value === id) selectedId.value = ''
    await reload()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onSaveAbilities() {
  if (!selected.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await setRoleNodes(selected.value.id, draftAbilities.value)
    roleNodes.value = {
      ...roleNodes.value,
      [selected.value.id]: res.nodes,
    }
    const abs = [...res.nodes].sort()
    draftAbilities.value = abs
    savedSnapshot.value = JSON.stringify(abs)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.roles-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.roles-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(240px, 320px) 1fr;
  gap: 12px;
}

.roles-left,
.roles-right {
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 14px 16px;
}

.pane-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.pane-head h1 {
  margin: 0;
  font-size: 1.2rem;
}

.pane-head .muted {
  margin: 4px 0 0;
  font-size: 0.85rem;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
  align-items: center;
}

.perm-search,
.modal .form select,
.modal .form > label > input {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 7px 9px;
  font: inherit;
  background: #fff;
}

.modal .form > label {
  display: grid;
  gap: 4px;
  margin-bottom: 10px;
  font-size: 0.85rem;
}

.modal .form > label:last-of-type {
  margin-bottom: 0;
}

.role-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  flex: 1;
  min-height: 0;
}

.role-item {
  display: grid;
  gap: 2px;
  padding: 10px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  margin-bottom: 4px;
}

.role-item:hover {
  background: #eef1f4;
}

.role-item.active {
  background: #eef6f3;
  border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
}

.role-item-main {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}

.role-item-main code,
.scope,
.ability-count {
  font-size: 0.78rem;
}

.empty,
.empty-right {
  padding: 24px 8px;
  text-align: center;
}

.empty-right {
  flex: 1;
  display: grid;
  place-items: center;
}

.perm-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.perm-search {
  width: min(280px, 100%);
}

.perm-groups {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.perm-group {
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  background: color-mix(in srgb, var(--panel) 90%, #eef1f4);
}

.group-head {
  margin-bottom: 8px;
}

.group-check {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.group-check .muted {
  font-size: 0.78rem;
}

.ability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px 10px;
}

.ability-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  cursor: pointer;
  min-width: 0;
}

.ability-name {
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
}

.assign-modal {
  width: min(640px, 92vw);
}

.assign-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  margin-top: 0px;
}

.assign-form .perm-toolbar {
  margin-bottom: 0;
}

.assign-user-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 6px 12px;
  max-height: min(420px, 55vh);
  overflow: auto;
  padding: 6px 2px;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--panel) 90%, #eef1f4);
}

.assign-user-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 4px 8px;
  font-size: 0.85rem;
  cursor: pointer;
  min-width: 0;
  border-radius: var(--radius-sm);
}

.assign-user-item input[type='checkbox'] {
  flex: 0 0 auto;
  margin: 0;
  width: 1rem;
  height: 1rem;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  accent-color: var(--accent, #3b6d11);
}

.assign-user-text {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}

.assign-user-name {
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assign-user-text code {
  font-size: 0.75rem;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) {
  .roles-split {
    grid-template-columns: 1fr;
    overflow: auto;
  }
  .roles-left {
    max-height: 280px;
  }
}
</style>
