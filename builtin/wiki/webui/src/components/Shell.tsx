import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  localizedAppLabel,
  localizedEntityLabel,
  type ManifestI18n,
} from '@modoor/hooks/shell'
import {
  fetchProfile,
  fetchShellModules,
  listProjects,
  logout,
  type WikiProject,
} from '../api/wiki'
import { useI18n } from '../useI18n'

type ShellModule = {
  id: string
  label: string
  href?: string
  path?: string
  i18n?: ManifestI18n
  menus?: { id: string; label: string; path: string; key?: string }[]
}

type OpenMenu = 'brand' | 'project' | 'inbox' | 'avatar' | null

type Props = {
  children: ReactNode
  /** default: top nav; workspace: no top bar (detail page uses sidebar chrome) */
  variant?: 'default' | 'workspace'
  className?: string
  project?: WikiProject | null
  projects?: WikiProject[]
  onEditProject?: () => void
  onCreateProject?: () => void
  /** Extra mid-section for workspace sidebar (page tree, etc.) */
  sidebarBody?: ReactNode
  /** Collapse / tools rendered in workspace sidebar pages head */
  sidebarPagesHead?: ReactNode
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return (name.slice(0, 2) || '?').toUpperCase()
}

export function Shell({
  children,
  variant = 'default',
  className = '',
  project = null,
  projects: projectsProp,
  onEditProject,
  onCreateProject,
  sidebarBody,
  sidebarPagesHead,
}: Props) {
  const navigate = useNavigate()
  const { t, locale, setLocale, SUPPORTED_LOCALES } = useI18n()
  const [user, setUser] = useState<{ login: string; display_name?: string } | null>(null)
  const [modules, setModules] = useState<ShellModule[]>([])
  const [projects, setProjects] = useState<WikiProject[]>(projectsProp || [])
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null)

  const wikiModule = useMemo(
    () => modules.find((m) => m.id === 'wiki') || { id: 'wiki', label: 'Wiki', menus: [] },
    [modules],
  )
  const wikiBrand = localizedAppLabel(wikiModule, locale, wikiModule.label || 'Wiki')
  const menus = useMemo(
    () =>
      (wikiModule.menus || []).map((item) => ({
        ...item,
        label: localizedEntityLabel(wikiModule.i18n, item, locale, item.label),
      })),
    [wikiModule, locale],
  )
  const userLabel = user?.display_name || user?.login || ''

  useEffect(() => {
    if (projectsProp) setProjects(projectsProp)
  }, [projectsProp])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const me = await fetchProfile()
        if (cancelled) return
        const u = me.user as {
          username?: string
          realname?: string
          login?: string
          display_name?: string
        }
        setUser({
          login: u.login || u.username || '',
          display_name: u.display_name || u.realname,
        })
        const cat = await fetchShellModules()
        if (cancelled) return
        setModules(cat.modules || [])
        if (!projectsProp) {
          const list = await listProjects()
          if (!cancelled) setProjects(list.items)
        }
      } catch {
        /* redirect handled in api */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectsProp])

  function closeMenus() {
    setOpenMenu(null)
  }

  function toggleMenu(name: Exclude<OpenMenu, null>) {
    setOpenMenu((cur) => (cur === name ? null : name))
  }

  function goModule(m: ShellModule) {
    closeMenus()
    if (m.id === 'wiki') {
      navigate('/')
      return
    }
    const href = m.href || m.path
    if (href && /^https?:\/\//i.test(href)) {
      location.href = href
      return
    }
    if (href) location.href = href.startsWith('/mod/') || href.startsWith('http') ? href : href
  }

  function goProject(p: WikiProject) {
    closeMenus()
    if (p.home_page_id) navigate(`/${p.home_page_id}`)
    else navigate('/')
  }

  async function onLogout() {
    closeMenus()
    await logout()
    location.href = '/login'
  }

  const logo = (
    <a className="shell-logo" href="/" aria-label="Modoor" onClick={closeMenus}>
      <img src="/logo.png" alt="" width="32" height="32" />
    </a>
  )

  const brandSwitcher = (
    <div
      className={`brand-wrap ${openMenu === 'brand' ? 'open' : ''}`}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="brand"
        aria-haspopup="listbox"
        aria-expanded={openMenu === 'brand'}
        onClick={() => toggleMenu('brand')}
      >
        <span className="brand-text">{wikiBrand}</span>
        <span className="caret">▾</span>
      </button>
      {openMenu === 'brand' ? (
        <div className="switcher" role="listbox">
          {modules.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`switcher-item ${m.id === 'wiki' ? 'active' : ''}`}
              role="option"
              onClick={() => goModule(m)}
            >
              {localizedAppLabel(m, locale, m.label)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )

  const projectSwitcher = project ? (
    <div
      className={`brand-wrap project-wrap ${openMenu === 'project' ? 'open' : ''}`}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="brand project-brand"
        aria-haspopup="listbox"
        aria-expanded={openMenu === 'project'}
        onClick={() => toggleMenu('project')}
      >
        <span className="project-brand-text">{project.name}</span>
        <span className="caret">▾</span>
      </button>
      {openMenu === 'project' ? (
        <div className="switcher project-switcher" role="listbox">
          <div className="switcher-hint">{t('wiki.switchProject')}</div>
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`switcher-item ${p.id === project.id ? 'active' : ''}`}
              role="option"
              onClick={() => goProject(p)}
            >
              <span>{p.name}</span>
            </button>
          ))}
          <div className="switcher-actions">
            {onEditProject ? (
              <button
                type="button"
                className="switcher-item"
                onClick={() => {
                  closeMenus()
                  onEditProject()
                }}
              >
                {t('wiki.editCurrent')}
              </button>
            ) : null}
            {onCreateProject ? (
              <button
                type="button"
                className="switcher-item"
                onClick={() => {
                  closeMenus()
                  onCreateProject()
                }}
              >
                {t('wiki.newProjectMenu')}
              </button>
            ) : (
              <button
                type="button"
                className="switcher-item"
                onClick={() => {
                  closeMenus()
                  navigate('/')
                }}
              >
                {t('wiki.allProjects')}
              </button>
            )}
          </div>
        </div>
      ) : null}
    </div>
  ) : null

  const gotoHomeButton = (
    <button
      type="button"
      className="sidebar-home-btn"
      title={t('wiki.home')}
      aria-label={t('wiki.home')}
      onClick={(e) => {
        e.stopPropagation()
        closeMenus()
        navigate('/')
      }}
    >
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z" />
      </svg>
    </button>
  )

  const languageMenu = (
    <>
      <div className="systray-menu-header lang-head">
        <div className="sub">{t('wiki.language')}</div>
      </div>
      {SUPPORTED_LOCALES.map((loc) => (
        <button
          key={loc.code}
          type="button"
          className={`menu-link${locale === loc.code ? ' active' : ''}`}
          role="menuitem"
          onClick={() => {
            setLocale(loc.code)
            closeMenus()
          }}
        >
          {loc.label}
        </button>
      ))}
      <div className="sep" />
    </>
  )

  const avatarBlock = user ? (
    <div
      className={`sidebar-user ${openMenu === 'avatar' ? 'open' : ''}`}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="sidebar-user-btn"
        aria-label="User menu"
        aria-haspopup="menu"
        aria-expanded={openMenu === 'avatar'}
        onClick={() => toggleMenu('avatar')}
      >
        <span className="avatar">{initials(userLabel)}</span>
        <span className="sidebar-user-meta">
          <span className="sidebar-user-name">{userLabel}</span>
        </span>
      </button>
      {openMenu === 'avatar' ? (
        <div className="systray-menu sidebar-user-menu" role="menu">
          <div className="systray-menu-header">
            <div className="name">{userLabel}</div>
            <div className="sub">{user.login}</div>
          </div>
          {languageMenu}
          <button type="button" className="menu-link" role="menuitem" onClick={onLogout}>
            {t('wiki.logout')}
          </button>
        </div>
      ) : null}
    </div>
  ) : (
    <a className="systray-login sidebar-login" href="/login">
      {t('wiki.login')}
    </a>
  )

  if (variant === 'workspace') {
    return (
      <div
        className={`shell shell--workspace${className ? ` ${className}` : ''}`}
        onClick={closeMenus}
      >
        <aside className="sidebar workspace-sidebar" aria-hidden={className.includes('is-collapsed')}>
          <div className="sidebar-chrome">
            <div className="sidebar-chrome-row">
              {logo}
              {brandSwitcher}
              <span className="sidebar-chrome-spacer" aria-hidden="true" />
              {projectSwitcher}
              {gotoHomeButton}
            </div>
          </div>
          {sidebarPagesHead}
          <div className="sidebar-body">{sidebarBody}</div>
          <div className="sidebar-foot">{avatarBlock}</div>
        </aside>
        <div className="main workspace-main">{children}</div>
      </div>
    )
  }

  return (
    <div className="shell" onClick={closeMenus}>
      <header className="top">
        {logo}
        {brandSwitcher}
        {projectSwitcher}
        <nav className="nav">
          {menus.map((item) => {
            const to = item.path?.replace(/^\/mod\/wiki/, '') || '/'
            const local = to === '' || to === '/' ? '/' : to.startsWith('/') ? to : `/${to}`
            return (
              <Link key={item.id} to={local} onClick={closeMenus}>
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="systray" onClick={(e) => e.stopPropagation()}>
          {user ? (
            <>
              <div className={`systray-item ${openMenu === 'inbox' ? 'open' : ''}`}>
                <button
                  type="button"
                  className="systray-btn"
                  aria-label="Inbox"
                  title="Inbox"
                  onClick={() => toggleMenu('inbox')}
                >
                  <svg
                    className="systray-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M6 9a6 6 0 1 1 12 0c0 3.2 1.2 4.8 2 6H4c.8-1.2 2-2.8 2-6" />
                    <path d="M10 19a2 2 0 0 0 4 0" />
                  </svg>
                </button>
                {openMenu === 'inbox' ? (
                  <div className="systray-menu wide" role="menu">
                    <div className="systray-menu-header">
                      <div className="name">Inbox</div>
                    </div>
                    <div className="systray-empty">{t('wiki.inboxEmpty')}</div>
                  </div>
                ) : null}
              </div>

              <div className={`systray-item ${openMenu === 'avatar' ? 'open' : ''}`}>
                <button
                  type="button"
                  className="systray-btn"
                  aria-label="User menu"
                  title={userLabel}
                  onClick={() => toggleMenu('avatar')}
                >
                  <span className="avatar">{initials(userLabel)}</span>
                </button>
                {openMenu === 'avatar' ? (
                  <div className="systray-menu" role="menu">
                    <div className="systray-menu-header">
                      <div className="name">{userLabel}</div>
                      <div className="sub">{user.login}</div>
                    </div>
                    {languageMenu}
                    <button type="button" className="menu-link" role="menuitem" onClick={onLogout}>
                      {t('wiki.logout')}
                    </button>
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <a className="systray-login" href="/login">
              {t('wiki.login')}
            </a>
          )}
        </div>
      </header>
      <div className="main">{children}</div>
    </div>
  )
}
