<template>
  <div class="shell" :class="{ 'nav-side': menuLayout === 'side' }" @click="closeMenus">
    <header class="top">
      <a class="shell-logo" href="/home" aria-label="Modoor">
        <img :src="logoSrc" alt="" width="32" height="32" />
      </a>
      <div class="brand-wrap" :class="{ open: openMenu === 'brand' }" @click.stop>
        <button
          class="brand"
          type="button"
          aria-haspopup="listbox"
          :aria-expanded="openMenu === 'brand'"
          @click="toggleMenu('brand')"
        >
          {{ currentLabel }}
          <span class="caret">▾</span>
        </button>
        <div v-if="openMenu === 'brand'" class="switcher" role="listbox">
          <button
            v-for="m in switcherModules"
            :key="m.id"
            type="button"
            class="switcher-item"
            :class="{ active: m.id === (shellModule?.id || activeModule), muted: m.online === false }"
            role="option"
            @click="goModule(m)"
          >
            <span>{{ m.label }}</span>
          </button>
        </div>
      </div>
      <nav v-if="user && menus.length && menuLayout === 'top'" class="nav">
        <template v-for="item in menus" :key="item.id">
          <div
            v-if="item.items?.length"
            class="nav-group"
            :class="{ 
              open: openNavGroup === item.id, 
              active: isNavGroupActive(item) 
            }"
            @mouseenter="openNavGroup = item.id"
            @mouseleave="openNavGroup = null"
            @focusin="openNavGroup = item.id"
            @focusout="onNavFocusOut($event, item.id)"
            @click.stop
          >
            <button
              type="button"
              class="nav-group-btn"
              :aria-expanded="openNavGroup === item.id"
            >
              {{ item.label }}
              <span class="caret">▾</span>
            </button>
            <div class="nav-group-menu" role="menu">
              <template v-for="sub in item.items" :key="sub.id">
                <div v-if="sub.items?.length" class="nav-subgroup">
                  <MenuLink
                    v-if="sub.path"
                    :to="sub.path"
                    :module-id="moduleId"
                    class="nav-subgroup-label"
                    role="menuitem"
                    @click="closeMenus"
                  >
                    {{ sub.label }}
                  </MenuLink>
                  <div v-else class="nav-subgroup-label">{{ sub.label }}</div>
                  <MenuLink
                    v-for="child in sub.items"
                    :key="child.id"
                    :to="child.path || '#'"
                    :module-id="moduleId"
                    class="nav-subchild"
                    role="menuitem"
                    @click="closeMenus"
                  >
                    {{ child.label }}
                  </MenuLink>
                </div>
                <MenuLink
                  v-else
                  :to="sub.path || '#'"
                  :module-id="moduleId"
                  role="menuitem"
                  @click="closeMenus"
                >
                  {{ sub.label }}
                </MenuLink>
              </template>
            </div>
          </div>
          <MenuLink v-else-if="item.path" :to="item.path" :module-id="moduleId">{{ item.label }}</MenuLink>
        </template>
      </nav>
      <div class="systray">
        <template v-if="user">
          <component :is="sysTrayWidget" v-if="sysTrayWidget" @click.stop />
          <div class="systray-item" @click.stop>
            <button
              v-if="false"
              type="button"
              class="systray-btn"
              :aria-label="t('shell.agentGuide')"
              :title="t('shell.agentGuide')"
              @click="openAgentGuide"
            >
              <SvgIcon class="systray-icon" name="agent" />
            </button>
          </div>

          <div
            class="systray-item"
            :class="{ open: openMenu === 'inbox' }"
            @click.stop
          >
            <button
              type="button"
              class="systray-btn"
              aria-haspopup="true"
              :aria-expanded="openMenu === 'inbox'"
              :aria-label="t('shell.inbox')"
              :title="t('shell.inbox')"
              @click="toggleMenu('inbox')"
            >
              <SvgIcon class="systray-icon" name="bell" />
              <span v-if="inboxCount > 0" class="systray-badge">{{ inboxCount }}</span>
            </button>
            <div v-if="openMenu === 'inbox'" class="systray-menu wide" role="menu">
              <div class="systray-menu-header">
                <div class="name">{{ t('shell.inbox') }}</div>
              </div>
              <a
                v-for="msg in inbox"
                :key="msg.id"
                :href="msg.href || '#'"
                role="menuitem"
                @click="closeMenus"
              >
                {{ msg.title }}
              </a>
              <div v-if="!inbox.length" class="systray-empty">{{ t('shell.inboxEmpty') }}</div>
            </div>
          </div>

          <div
            v-if="switchRoles.length"
            class="systray-item"
            :class="{ open: openMenu === 'role' }"
            @click.stop
          >
            <button
              type="button"
              class="systray-btn"
              aria-haspopup="true"
              :aria-expanded="openMenu === 'role'"
              :aria-label="t('shell.role')"
              :title="t('shell.role')"
              @click="toggleMenu('role')"
            >
              <SvgIcon class="systray-icon" name="shield" />
              <span class="role-label">{{ roleName }}</span>
            </button>
            <div v-if="openMenu === 'role'" class="systray-menu" role="menu">
              <div class="systray-menu-header">
                <div class="name">{{ t('shell.role') }}</div>
              </div>
              <button
                v-for="role in switchRoles"
                :key="role.code"
                type="button"
                class="menu-link"
                :class="{ active: role.code === activeRole }"
                role="menuitem"
                @click="selectRole(role)"
              >
                {{ role.name }}
              </button>
            </div>
          </div>

          <div
            v-if="tenants.length > 1"
            class="systray-item"
            :class="{ open: openMenu === 'tenant' }"
            @click.stop
          >
            <button
              type="button"
              class="systray-btn"
              aria-haspopup="true"
              :aria-expanded="openMenu === 'tenant'"
              :aria-label="t('shell.tenant')"
              :title="t('shell.tenant')"
              @click="toggleMenu('tenant')"
            >
              <SvgIcon class="systray-icon" name="building" />
              <span class="tenant-label">{{ tenantName }}</span>
            </button>
            <div v-if="openMenu === 'tenant'" class="systray-menu" role="menu">
              <div class="systray-menu-header">
                <div class="name">{{ t('shell.workspace') }}</div>
              </div>
              <button
                v-for="tn in tenants"
                :key="tn.id"
                type="button"
                class="menu-link"
                :class="{ active: tn.id === tenantId }"
                role="menuitem"
                @click="selectTenant(tn)"
              >
                {{ tn.name }}
              </button>
            </div>
          </div>

          <div
            class="systray-item"
            :class="{ open: openMenu === 'avatar' }"
            @click.stop
          >
            <button
              type="button"
              class="systray-btn"
              aria-haspopup="true"
              :aria-expanded="openMenu === 'avatar'"
              aria-label="User menu"
              :title="user.realname || user.username"
              @click="toggleMenu('avatar')"
            >
              <span class="avatar">{{ userInitials }}</span>
            </button>
            <div v-if="openMenu === 'avatar'" class="systray-menu" role="menu">
              <div class="systray-menu-header">
                <div class="name">{{ user.realname }}</div>
                <div class="sub">{{ tenantName }}</div>
              </div>
              <button type="button" class="menu-link" role="menuitem" @click="openAgentConnect">
                {{ t('shell.connectAgentGuide') }}
              </button>
              <div class="sep" />
              <button type="button" class="menu-link" role="menuitem" @click="openUserSettings">
                {{ t('shell.userSettings') }}
              </button>
              <a href="/profile" class="menu-link" role="menuitem" @click="closeMenus">
                {{ t('shell.userProfile') }}
              </a>
              <div class="sep" />
              <button type="button" class="menu-link" role="menuitem" @click="onLogout">
                {{ t('shell.logout') }}
              </button>
            </div>
          </div>
        </template>
        <a v-else class="systray-login" :href="loginHref">{{ t('shell.login') }}</a>
      </div>
    </header>

    <div class="shell-body">
      <aside v-if="user && menus.length && menuLayout === 'side'" class="side-nav" @click.stop>
        <template v-for="item in menus" :key="item.id">
          <div
            v-if="item.items?.length"
            class="side-group"
            :class="{ open: isSideGroupOpen(item.id), active: isNavGroupActive(item) }"
          >
            <button
              type="button"
              class="side-group-toggle"
              :aria-expanded="isSideGroupOpen(item.id)"
              @click="toggleSideGroup(item.id)"
            >
              <span>{{ item.label }}</span>
              <span class="caret" aria-hidden="true">{{ isSideGroupOpen(item.id) ? '▾' : '▸' }}</span>
            </button>
            <div v-show="isSideGroupOpen(item.id)" class="side-group-body">
              <template v-for="sub in item.items" :key="sub.id">
                <div v-if="sub.items?.length" class="side-subgroup">
                  <MenuLink
                    v-if="sub.path"
                    :to="sub.path"
                    :module-id="moduleId"
                    class="side-link"
                    @click="closeMenus"
                  >
                    {{ sub.label }}
                  </MenuLink>
                  <div v-else class="side-link side-subgroup-label">{{ sub.label }}</div>
                  <MenuLink
                    v-for="child in sub.items"
                    :key="child.id"
                    :to="child.path || '#'"
                    :module-id="moduleId"
                    class="side-link side-sublink"
                    @click="closeMenus"
                  >
                    {{ child.label }}
                  </MenuLink>
                </div>
                <MenuLink
                  v-else
                  :to="sub.path || '#'"
                  :module-id="moduleId"
                  class="side-link"
                  @click="closeMenus"
                >
                  {{ sub.label }}
                </MenuLink>
              </template>
            </div>
          </div>
          <MenuLink
            v-else-if="item.path"
            :to="item.path"
            :module-id="moduleId"
            class="side-link side-top-link"
            @click="closeMenus"
          >
            {{ item.label }}
          </MenuLink>
        </template>
      </aside>
      <main class="main">
        <slot />
      </main>
    </div>

    <div
      v-if="userSettingsOpen"
      class="modal-mask"
      @click.self="userSettingsOpen = false"
    >
      <div
        class="modal user-settings-modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="userSettingsTitleId"
        @click.stop
      >
        <header class="modal-head">
          <strong :id="userSettingsTitleId">{{ t('shell.settingsTitle') }}</strong>
          <button type="button" class="btn" @click="userSettingsOpen = false">
            {{ t('shell.close') }}
          </button>
        </header>
        <div class="user-settings-body">
          <label class="settings-field">
            <span class="settings-label">{{ t('shell.menuLayout') }}</span>
            <span class="settings-hint">{{ t('shell.menuLayoutHint') }}</span>
            <div class="settings-options">
              <label class="settings-option">
                <input v-model="draftMenuLayout" type="radio" value="" />
                <span>{{ t('shell.menuLayoutFollow') }}</span>
              </label>
              <label class="settings-option">
                <input v-model="draftMenuLayout" type="radio" value="top" />
                <span>{{ t('shell.menuLayoutTop') }}</span>
              </label>
              <label class="settings-option">
                <input v-model="draftMenuLayout" type="radio" value="side" />
                <span>{{ t('shell.menuLayoutSide') }}</span>
              </label>
            </div>
          </label>

          <label class="settings-field">
            <span class="settings-label">{{ t('shell.theme') }}</span>
            <select class="settings-select" disabled :value="'system'">
              <option value="system">{{ t('shell.themeSystem') }}</option>
            </select>
            <span class="settings-hint">{{ t('shell.themeHint') }}</span>
          </label>

          <div class="modal-actions pad-actions">
            <div class="pad-spacer" />
            <button type="button" class="btn" @click="userSettingsOpen = false">
              {{ t('shell.close') }}
            </button>
            <button type="button" class="btn primary" @click="applyUserSettings">
              {{ t('shell.saveSettings') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="agentGuideOpen"
      class="modal-mask"
      @click.self="agentGuideOpen = false"
    >
      <div
        class="modal agent-connect-modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="agentGuideTitleId"
        @click.stop
      >
        <header class="modal-head">
          <strong :id="agentGuideTitleId">{{ t('shell.agentGuide') }}</strong>
          <button type="button" class="btn" @click="agentGuideOpen = false">
            {{ t('shell.close') }}
          </button>
        </header>
        <div class="agent-connect-body">
          <p class="muted">{{ t('shell.agentGuideIntro') }}</p>
          <p v-if="agentConnectError" class="error">{{ agentConnectError }}</p>
          <pre class="agent-connect-code agent-guide-doc">{{ agentGuideDoc }}</pre>
          <!-- <p class="muted">
            <a :href="agentReadmeUrl" target="_blank" rel="noopener">{{ agentReadmeUrl }}</a>
          </p> -->
          <div class="modal-actions pad-actions">
            <button type="button" class="btn" @click="openAgentConnectFromGuide">
              {{ t('shell.connectAgentGuide') }}
            </button>
            <div class="pad-spacer" />
            <button type="button" class="btn" :disabled="!agentGuideDoc" @click="copyAgentGuide">
              {{ guideCopyDone ? t('shell.copied') : t('shell.copyGuide') }}
            </button>
            <button type="button" class="btn primary" @click="agentGuideOpen = false">
              {{ t('shell.gotIt') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="agentConnectOpen"
      class="modal-mask"
      @click.self="agentConnectOpen = false"
    >
      <div
        class="modal agent-connect-modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="agentConnectTitleId"
        @click.stop
      >
        <header class="modal-head">
          <strong :id="agentConnectTitleId">{{ t('shell.connectAgentGuide') }}</strong>
          <button type="button" class="btn" @click="agentConnectOpen = false">
            {{ t('shell.close') }}
          </button>
        </header>
        <div class="agent-connect-body">
          <p>{{ t('shell.connectAgentIntro') }}</p>
          <p class="muted">{{ t('shell.connectAgentClients') }}</p>
          <p v-if="agentConnectError" class="error">{{ agentConnectError }}</p>
          <template v-else-if="agentConnect">
            <h3>{{ t('shell.connectAgentConfig') }}</h3>
            <!-- <p class="muted">{{ t('shell.connectAgentMcpHint') }}</p> -->
            <label class="agent-readonly">
              <input
                type="checkbox"
                :checked="agentConnect.agent_readonly"
                :disabled="agentBusy"
                @change="onToggleReadonly(($event.target as HTMLInputElement).checked)"
              />
              <span>{{ t('shell.agentReadonly') }}</span>
            </label>
            <p class="muted">{{ t('shell.agentReadonlyHint') }}</p>
            <!-- <label class="agent-field">
              <span>{{ t('shell.mcpUrl') }}</span>
              <code>{{ agentConnect.mcp_url }}</code>
            </label>
            <label class="agent-field">
              <span>{{ t('shell.agentKey') }}</span>
              <code>{{ agentConnect.agent_key }}</code>
            </label> -->
            <pre class="agent-connect-code">{{ mcpSnippetWithKey }}</pre>
            <div class="modal-actions pad-actions">
              <button type="button" class="btn" :disabled="agentBusy" @click="onRotateAgentKey">
                {{ t('shell.rotateKey') }}
              </button>
              <div class="pad-spacer" />
              <button type="button" class="btn" @click="copyMcpSnippet">
                {{ copyDone ? t('shell.copied') : t('shell.copyConfig') }}
              </button>
              <button type="button" class="btn primary" @click="agentConnectOpen = false">
                {{ t('shell.gotIt') }}
              </button>
            </div>
          </template>
          <p v-else class="muted">{{ t('shell.loading') }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SvgIcon from '@modoor/widget/SvgIcon'
import MenuLink from './MenuLink.vue'
import { resolveSysTrayWidget } from './sysTray'
import { provideRecordGateway } from '../recordGateway'
import {
  fetchProfile,
  readRoleCookie,
  writeActingRole,
  clearActingRole,
  resolveActingRole,
  fetchAgentConnect,
  rotateAgentKey,
  setAgentReadonly,
  switchTenant,
  logout as apiLogout,
  fetchShellCatalog,
  shellLoginUrl,
  useI18n,
  setLocale,
  fetchGlobalSettings,
  useUserPrefs,
  localizedAppLabel,
  localizedEntityLabel,
  setShellDocumentTitle,
  type AuthUser,
  type SwitchRole,
  type AgentConnectInfo,
  type ShellModule,
  type MenuLayout,
} from '@modoor/hooks'

provideRecordGateway()

type InboxMessage = { id: string; title: string; href?: string }
type TenantOption = { id: string; name: string }
type OpenMenu = 'brand' | 'inbox' | 'tenant' | 'role' | 'avatar' | null
type NavMenu = {
  id: string
  label: string
  path?: string
  items?: NavMenu[]
}

const props = defineProps<{
  /** Current module id (base / wiki / sale / …) */
  moduleId: string
}>()

const { t, locale } = useI18n()
const { prefs, setModuleMenuLayout } = useUserPrefs()
const router = useRouter()
const route = useRoute()
const user = ref<AuthUser | null>(null)
const modules = ref<ShellModule[]>([])
const tenantId = ref('')
const tenants = ref<TenantOption[]>([])
const switchRoles = ref<SwitchRole[]>([])
const activeRole = ref('')
const inbox = ref<InboxMessage[]>([])
const openMenu = ref<OpenMenu>(null)
const openNavGroup = ref<string | null>(null)
/** 左侧分组展开状态。切到左侧导航时只展开当前页面所在分组 */
const openSideGroups = ref<Set<string>>(new Set())
const activeModule = ref(props.moduleId)
/** 目录接口给出的壳层身份。被融合的模块跟声明方走。 */
const shellModule = computed(() => {
  const current = modules.value.find((item) => {
    return item.id === activeModule.value
  })
  const shellId = current?.shell
  if (!shellId) return current
  const find = modules.value.find((item) => {
    return item.id === shellId
  })
  return find || current
})
const menuLayout = computed(() => {
  const mid = String(shellModule.value?.id || props.moduleId || '').trim()
  const personal = mid ? prefs.value.moduleMenus[mid] : undefined
  if (personal === 'side' || personal === 'top') return personal
  return shellModule.value?.menuLayout === 'side' ? 'side' : 'top'
})
const sysTrayWidget = computed(() => resolveSysTrayWidget(activeModule.value || props.moduleId))
const logoSrc = '/logo.png'
const agentConnectOpen = ref(false)
const copyDone = ref(false)
const guideCopyDone = ref(false)
const agentBusy = ref(false)
const agentConnectError = ref('')
const agentConnect = ref<AgentConnectInfo | null>(null)
const agentGuideOpen = ref(false)
const userSettingsOpen = ref(false)
const draftMenuLayout = ref<MenuLayout | ''>('')
const agentGuideTitleId = 'shell-agent-guide-title'
const agentConnectTitleId = 'shell-agent-connect-title'
const userSettingsTitleId = 'shell-user-settings-title'

const mcpSnippet = computed(() => {
  const info = agentConnect.value
  if (!info) return ''
  return JSON.stringify(info.snippet, null, 2)
})

/** Prefer Bearer token config — more reliable than OAuth on some hosts. */
const mcpSnippetWithKey = computed(() => {
  const info = agentConnect.value
  if (!info) return ''
  const withKey = info.snippet_with_key
  if (withKey) return JSON.stringify(withKey, null, 2)
  if (info.mcp_url && info.agent_key) {
    return JSON.stringify(
      {
        mcpServers: {
          modoor: {
            url: info.mcp_url,
            headers: { Authorization: `Bearer ${info.agent_key}` },
          },
        },
      },
      null,
      2,
    )
  }
  return mcpSnippet.value
})

const agentBase = computed(() => {
  const mcp = agentConnect.value?.mcp_url || ''
  if (mcp.endsWith('/mcp')) return mcp.slice(0, -4)
  if (typeof window !== 'undefined') return window.location.origin
  return 'http://127.0.0.1:8765'
})

/** Short paste for Codex / WorkBuddy / Cursor — points at /agent/readme */
const agentGuideDoc = computed(() => {
  const base = agentBase.value
  return [
    `请按 modoor(木牍) 中的说明安装：${base}/agent/readme`,
    `- 先安装其中列出的每个 Skill URL。`,
    `- 再连接 MCP：${base}/mcp，且仅调用 Skill 中声明的 tools。`,
  ].join('\n')
})

const currentLabel = computed(() =>
  localizedAppLabel(shellModule.value, locale.value, 'Modoor'),
)

function localizeMenu(
  item: { id: string; label: string; path?: string; items?: NavMenu[]; key?: string },
  i18n: ShellModule['i18n'],
): NavMenu {
  return {
    id: item.id,
    path: item.path,
    label: localizedEntityLabel(i18n, item, locale.value, item.label),
    items: (item.items || []).map((c) => localizeMenu(c, i18n)),
  }
}

const menus = computed(() => {
  const hit = shellModule.value
  return (hit?.menus || []).map((item) => localizeMenu(item, hit?.i18n))
})

const switcherModules = computed(() =>
  modules.value
    .filter((mod) => mod.listed !== false)
    .map((m) => ({
      ...m,
      label: localizedAppLabel(m, locale.value, m.label),
    })),
)

const tenantName = computed(() => {
  const hit = tenants.value.find((tn) => tn.id === tenantId.value)
  return hit?.name || tenantId.value || '—'
})

function pageNameForPath(path: string) {
  let best = ''
  let bestLen = -1
  const walk = (item: NavMenu) => {
    const menuPath = item.path || ''
    if (menuPath && (path === menuPath || path.startsWith(menuPath + '/'))) {
      if (menuPath.length >= bestLen) {
        bestLen = menuPath.length
        best = item.label
      }
    }
    for (const child of item.items || []) walk(child)
  }
  for (const item of menus.value) walk(item)
  return best || currentLabel.value
}

watch(
  () => [route.fullPath, pageNameForPath(route.path), tenantName.value] as const,
  ([, page, tenant]) => {
    if (!page) return
    setShellDocumentTitle(page, tenant === '—' ? '' : tenant)
  },
  { immediate: true },
)
const roleName = computed(() => {
  if (!activeRole.value) return t('shell.switchRole')
  const hit = switchRoles.value.find((role) => {
    return role.code === activeRole.value
  })
  return hit?.name || activeRole.value
})

const inboxCount = computed(() => inbox.value.length)

const userInitials = computed(() => {
  const name = (user.value?.realname || user.value?.username || '?').trim()
  const parts = name.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
})

const loginHref = computed(() => shellLoginUrl())

function detectActive() {
  activeModule.value = props.moduleId
  const path = route.path
  for (const m of modules.value) {
    if (m.path && path.startsWith(m.path)) {
      activeModule.value = m.id
      break
    }
  }
}

function closeMenus() {
  openMenu.value = null
  openNavGroup.value = null
}

function toggleMenu(name: Exclude<OpenMenu, null>) {
  openNavGroup.value = null
  openMenu.value = openMenu.value === name ? null : name
}

function onNavFocusOut(event: FocusEvent, id: string) {
  const next = event.relatedTarget
  const host = event.currentTarget
  if (host instanceof HTMLElement && next instanceof Node && host.contains(next)) return
  if (openNavGroup.value === id) openNavGroup.value = null
}

function isSideGroupOpen(id: string) {
  return openSideGroups.value.has(id)
}

function toggleSideGroup(id: string) {
  const next = new Set(openSideGroups.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  openSideGroups.value = next
}

/** 菜单或布局变化时，只展开当前路由所在的分组 */
function syncSideGroupDefaults() {
  const next = new Set<string>()
  for (const item of menus.value) {
    if (item.items?.length && isNavGroupActive(item)) next.add(item.id)
  }
  openSideGroups.value = next
}

function ensureActiveSideGroupOpen() {
  let changed = false
  const next = new Set(openSideGroups.value)
  for (const item of menus.value) {
    if (item.items?.length && isNavGroupActive(item) && !next.has(item.id)) {
      next.add(item.id)
      changed = true
    }
  }
  if (changed) openSideGroups.value = next
}

function menuHitsPath(item: NavMenu, path: string): boolean {
  const p = item.path || ''
  if (p && (path === p || path.startsWith(p + '/'))) return true
  return (item.items || []).some((sub) => menuHitsPath(sub, path))
}

function isNavGroupActive(item: NavMenu) {
  return (item.items || []).some((sub) => menuHitsPath(sub, route.path))
}

async function refresh() {
  try {
    const profile = await fetchProfile()
    user.value = profile.user
    const roles = profile.user.switch_roles || []
    if (roles.length && profile.user.id != null) {
      const before = readRoleCookie()
      const next = resolveActingRole(profile.user.id, roles)
      writeActingRole(profile.user.id, next)
      switchRoles.value = roles
      activeRole.value = next
      if (before !== next) {
        location.reload()
        return
      }
    } else if (readRoleCookie()) {
      clearActingRole()
      switchRoles.value = []
      activeRole.value = ''
      location.reload()
      return
    } else {
      switchRoles.value = []
      activeRole.value = ''
    }
    const cat = await fetchShellCatalog()
    modules.value = cat.modules || []
    const tid = String(profile.user.tenant ?? cat.tenant?.id ?? '')
    tenantId.value = tid
    const fromProfile = (profile.user.tenants || []).map((tn) => ({
      id: String(tn.id),
      name: String(tn.name),
    }))
    tenants.value =
      fromProfile.length > 0
        ? fromProfile
        : [
            {
              id: tid,
              name: String(cat.tenant?.name || tid),
            },
          ]
    inbox.value = []
    detectActive()
    const visible = modules.value
    if (
      visible.length > 0 &&
      !visible.some((m) => m.id === props.moduleId || m.id === activeModule.value)
    ) {
      location.href = '/home'
      return
    }
  } catch {
    user.value = null
    modules.value = []
    tenants.value = []
    switchRoles.value = []
    activeRole.value = ''
    inbox.value = []
  }
}

function selectRole(role: SwitchRole) {
  if (!user.value) {
    closeMenus()
    return
  }
  // 仅一项时不允许清空（否则首页无模块且再也选不回）
  const canSwitch = switchRoles.value.length > 1;
  const isCurrent = role.code === activeRole.value;
  const next = isCurrent && canSwitch ? '' : role.code
  writeActingRole(user.value.id, next)
  closeMenus()
  location.reload()
}

function goModule(m: ShellModule) {
  closeMenus()
  if (m.id !== props.moduleId) {
    if (m.href && /^https?:\/\//i.test(m.href)) {
      location.href = m.href
      return
    }
    if (m.path) location.href = m.path
    return
  }
  activeModule.value = m.id
  const local = m.menus?.[0]?.path || m.path
  if (local) router.push(local)
}

async function selectTenant(tn: TenantOption) {
  if (tn.id === tenantId.value) {
    closeMenus()
    return
  }
  closeMenus()
  const res = await switchTenant(tn.id)
  // 切租户后 user id 变了，按新租户的 switch_roles 重写 acting role（超管默认 SUPERUSER）
  const nextUser = res.user
  const roles = nextUser?.switch_roles || []
  if (roles.length && nextUser?.id != null) {
    writeActingRole(nextUser.id, resolveActingRole(nextUser.id, roles))
  }
  location.href = res.home || '/'
}

function layoutModuleId() {
  return String(shellModule.value?.id || props.moduleId || '').trim()
}

function openUserSettings() {
  closeMenus()
  const mid = layoutModuleId()
  const personal = mid ? prefs.value.moduleMenus[mid] : undefined
  draftMenuLayout.value = personal === 'side' || personal === 'top' ? personal : ''
  userSettingsOpen.value = true
}

function applyUserSettings() {
  const mid = layoutModuleId()
  setModuleMenuLayout(mid, draftMenuLayout.value || null)
  userSettingsOpen.value = false
}

void loadCompanySettings()

async function loadCompanySettings() {
  try {
    const res = await fetchGlobalSettings()
    setLocale(res.settings.locale)
  } catch {
    /* keep the cached company settings */
  }
}

function openAgentGuide() {
  closeMenus()
  guideCopyDone.value = false
  agentConnectError.value = ''
  agentGuideOpen.value = true
  if (!agentConnect.value) void loadAgentConnect()
}

function openAgentConnectFromGuide() {
  agentGuideOpen.value = false
  openAgentConnect()
}

function openAgentConnect() {
  closeMenus()
  copyDone.value = false
  agentConnectError.value = ''
  agentConnect.value = null
  agentConnectOpen.value = true
  void loadAgentConnect()
}

async function loadAgentConnect() {
  try {
    agentConnect.value = await fetchAgentConnect()
  } catch (e) {
    agentConnectError.value = e instanceof Error ? e.message : String(e)
  }
}

async function onRotateAgentKey() {
  agentBusy.value = true
  agentConnectError.value = ''
  try {
    const res = await rotateAgentKey()
    if (agentConnect.value) {
      agentConnect.value = {
        ...agentConnect.value,
        agent_key: res.agent_key,
        agent_readonly:
          res.agent_readonly ?? agentConnect.value.agent_readonly,
        snippet: {
          mcpServers: {
            modoor: {
              url: agentConnect.value.mcp_url,
            },
          },
        },
        snippet_with_key: {
          mcpServers: {
            modoor: {
              url: agentConnect.value.mcp_url,
              headers: { Authorization: `Bearer ${res.agent_key}` },
            },
          },
        },
      }
    } else {
      await loadAgentConnect()
    }
  } catch (e) {
    agentConnectError.value = e instanceof Error ? e.message : String(e)
  } finally {
    agentBusy.value = false
  }
}

async function onToggleReadonly(readonly: boolean) {
  agentBusy.value = true
  agentConnectError.value = ''
  try {
    const res = await setAgentReadonly(readonly)
    if (agentConnect.value) {
      agentConnect.value = {
        ...agentConnect.value,
        agent_readonly: res.agent_readonly,
      }
    }
  } catch (e) {
    agentConnectError.value = e instanceof Error ? e.message : String(e)
    await loadAgentConnect()
  } finally {
    agentBusy.value = false
  }
}

async function copyMcpSnippet() {
  const text = mcpSnippetWithKey.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copyDone.value = true
    window.setTimeout(() => {
      copyDone.value = false
    }, 2000)
  } catch {
    copyDone.value = false
  }
}

async function copyAgentGuide() {
  const text = agentGuideDoc.value
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    guideCopyDone.value = true
    window.setTimeout(() => {
      guideCopyDone.value = false
    }, 2000)
  } catch {
    guideCopyDone.value = false
  }
}

async function onLogout() {
  closeMenus()
  await apiLogout()
  user.value = null
  location.href = shellLoginUrl()
}

watch(() => route.path, () => {
  detectActive()
  closeMenus()
  if (menuLayout.value === 'side') ensureActiveSideGroupOpen()
})
watch(() => props.moduleId, detectActive)
watch(
  () => [menuLayout.value, menus.value.map((m) => m.id).join('|')].join(':'),
  () => {
    if (menuLayout.value === 'side') syncSideGroupDefaults()
  },
)
onMounted(refresh)
</script>

<style scoped>
.agent-connect-modal {
  width: min(560px, 100%);
}
.user-settings-modal {
  width: min(420px, 100%);
}
.user-settings-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.settings-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.9rem;
}
.settings-label {
  font-weight: 600;
  color: var(--ink, #1c1914);
}
.settings-options {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 18px;
}
.settings-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-weight: 400;
  color: var(--ink, #1c1914);
}
.settings-select {
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  font: inherit;
  background: #fff;
  color: var(--ink, #1c1914);
}
.settings-select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  background: #eef1f4;
}
.settings-hint {
  font-size: 0.8rem;
  color: var(--muted, #6b6458);
}
.agent-connect-body {
  padding: 16px;
}
.agent-connect-body p {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.5;
}
.agent-connect-body h3 {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.agent-connect-body .muted {
  color: var(--muted, #6b6458);
  font-size: 13px;
}
.agent-connect-body .error {
  color: var(--danger, #b42318);
  font-size: 13px;
}
.agent-readonly {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 4px;
  font-size: 13px;
  font-weight: 500;
}
.agent-readonly input {
  width: 16px;
  height: 16px;
}
.agent-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted, #6b6458);
}
.agent-field code {
  font-size: 12px;
  word-break: break-all;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line, #e2e6eb);
  background: var(--bg, #f5f7f9);
  color: var(--ink, #1c1917);
}
.agent-connect-code {
  margin: 0 0 16px;
  padding: 12px 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--line, #e2e6eb);
  background: var(--bg, #f5f7f9);
  color: var(--ink, #1c1917);
  font-size: 12px;
  line-height: 1.45;
  overflow: auto;
  white-space: pre;
}
.pad-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pad-spacer {
  flex: 1;
  min-width: 8px;
}
.agent-guide-doc {
  max-height: min(52vh, 420px);
}
</style>
