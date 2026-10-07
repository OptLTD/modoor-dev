import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createPage,
  createProject,
  deletePage,
  getPage,
  getProject,
  getTree,
  listProjects,
  movePage,
  updatePage,
  updateProject,
  type TreeNode,
  type WikiPage,
  type WikiProject,
} from '../api/wiki'
import { BlockEditor, type BlockEditorHandle } from '../components/BlockEditor'
import { PageTree } from '../components/PageTree'
import { ProjectModal } from '../components/ProjectModal'
import { Shell } from '../components/Shell'
import { useI18n } from '../useI18n'

export function PageWorkspace() {
  const { pageId = '' } = useParams()
  const navigate = useNavigate()
  const { t, locale } = useI18n()
  const [project, setProject] = useState<WikiProject | null>(null)
  const [page, setPage] = useState<WikiPage | null>(null)
  const [tree, setTree] = useState<TreeNode[]>([])
  const [title, setTitle] = useState('')
  const [saveHint, setSaveHint] = useState(() => t('wiki.synced'))
  const [error, setError] = useState('')
  const [editProjectOpen, setEditProjectOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try {
      return localStorage.getItem('wiki.sidebar.open') !== '0'
    } catch {
      return true
    }
  })

  const [projects, setProjects] = useState<WikiProject[]>([])
  const [createProjectOpen, setCreateProjectOpen] = useState(false)
  const [toast, setToast] = useState('')
  const editorRef = useRef<BlockEditorHandle>(null)
  const toastTimer = useRef<number | null>(null)
  const savingRef = useRef(false)

  const showToast = useCallback((message: string) => {
    setToast(message)
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(''), 1800)
  }, [])

  function toggleSidebar() {
    setSidebarOpen((open) => {
      const next = !open
      try {
        localStorage.setItem('wiki.sidebar.open', next ? '1' : '0')
      } catch {
        /* ignore */
      }
      return next
    })
  }

  const reloadTree = useCallback(async (projectId: string) => {
    const res = await getTree(projectId)
    setTree(res.tree)
  }, [])

  const reloadProjects = useCallback(async () => {
    const res = await listProjects()
    setProjects(res.items)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setError('')
      try {
        const { page: p } = await getPage(pageId)
        if (cancelled) return
        setPage(p)
        setTitle(p.title)
        setSaveHint(t('wiki.synced'))
        const [{ project: proj }] = await Promise.all([
          getProject(p.project_id),
          reloadProjects(),
        ])
        if (cancelled) return
        setProject(proj)
        await reloadTree(p.project_id)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [pageId, reloadTree, reloadProjects, t])

  async function saveTitle(next: string) {
    if (!page || next === page.title) return
    setSaveHint(t('wiki.savingHint'))
    try {
      const res = await updatePage(page.id, { title: next })
      setPage(res.page)
      setSaveHint(t('wiki.saved'))
      if (project) await reloadTree(project.id)
    } catch (e) {
      setSaveHint(t('wiki.saveFailed'))
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function saveBody(json: string) {
    if (!page) return
    setSaveHint(t('wiki.savingHint'))
    try {
      const res = await updatePage(page.id, { body: json })
      setPage(res.page)
      setSaveHint(t('wiki.saved'))
    } catch (e) {
      setSaveHint(t('wiki.saveFailed'))
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const saveNow = useCallback(async () => {
    if (!page || savingRef.current) return
    savingRef.current = true
    const nextTitle = title.trim() || t('wiki.untitled')
    const bodyJson = editorRef.current?.flush() ?? (page.body || '[]')
    setSaveHint(t('wiki.savingHint'))
    showToast(t('wiki.savingToast'))
    try {
      const payload: { title?: string; body?: string } = { body: bodyJson }
      if (nextTitle !== page.title) payload.title = nextTitle
      const res = await updatePage(page.id, payload)
      setPage(res.page)
      if (payload.title) setTitle(res.page.title)
      setSaveHint(t('wiki.saved'))
      showToast(t('wiki.saved'))
      if (payload.title && project) await reloadTree(project.id)
    } catch (e) {
      setSaveHint(t('wiki.saveFailed'))
      const msg = e instanceof Error ? e.message : String(e)
      setError(msg)
      showToast(t('wiki.saveFailed'))
    } finally {
      savingRef.current = false
    }
  }, [page, title, project, reloadTree, showToast, t])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      if (e.key.toLowerCase() !== 's') return
      e.preventDefault()
      void saveNow()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [saveNow])

  useEffect(() => {
    return () => {
      if (toastTimer.current) window.clearTimeout(toastTimer.current)
    }
  }, [])

  async function onAddChild(parentId: string | null) {
    if (!project) return
    const res = await createPage({
      project_id: project.id,
      title: t('wiki.untitled'),
      parent_id: parentId,
    })
    await reloadTree(project.id)
    navigate(`/${res.page.id}`)
  }

  async function onDelete(id: string) {
    if (!project || !confirm(t('wiki.confirmDeletePage'))) return
    await deletePage(id)
    await reloadTree(project.id)
    if (id === pageId && project.home_page_id) navigate(`/${project.home_page_id}`)
  }

  async function onMove(id: string, parentId: string | null, sortOrder: number) {
    if (!project) return
    try {
      await movePage(id, { parent_id: parentId, sort_order: sortOrder })
      await reloadTree(project.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function onEditProject(values: { name: string; description: string }) {
    if (!project) return
    setBusy(true)
    try {
      const res = await updateProject(project.id, values)
      setProject(res.project)
      setEditProjectOpen(false)
      await reloadProjects()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onCreateProject(values: { name: string; description: string }) {
    setBusy(true)
    setError('')
    try {
      const res = await createProject(values)
      setCreateProjectOpen(false)
      await reloadProjects()
      const home = res.home_page?.id || res.project.home_page_id
      if (home) navigate(`/${home}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (error && !page) {
    return (
      <div className="workspace-boot">
        <p className="error">{error}</p>
        <button type="button" className="btn" onClick={() => navigate('/')}>
          {t('wiki.backProjects')}
        </button>
      </div>
    )
  }

  if (!page || !project) {
    return (
      <div className="workspace-boot" aria-busy="true" aria-live="polite">
        <div className="workspace-boot-spinner" />
        <p>{t('wiki.loading')}</p>
      </div>
    )
  }

  return (
    <Shell
      variant="workspace"
      className={sidebarOpen ? '' : 'is-collapsed'}
      project={project}
      projects={projects}
      onEditProject={() => setEditProjectOpen(true)}
      onCreateProject={() => setCreateProjectOpen(true)}
      sidebarPagesHead={
        <div className="sidebar-head">
          <span>{t('wiki.pages')}</span>
          <div className="sidebar-head-actions">
            <button
              type="button"
              className="btn icon"
              title={t('wiki.newPage')}
              aria-label={t('wiki.newPage')}
              onClick={() => onAddChild(null)}
            >
              +
            </button>
            <button
              type="button"
              className="btn icon"
              title={t('wiki.collapseSidebar')}
              aria-label={t('wiki.collapseSidebar')}
              onClick={toggleSidebar}
            >
              «
            </button>
          </div>
        </div>
      }
      sidebarBody={
        <PageTree
          tree={tree}
          activeId={page.id}
          homePageId={project.home_page_id}
          onSelect={(id) => navigate(`/${id}`)}
          onAddChild={onAddChild}
          onDelete={onDelete}
          onMove={onMove}
        />
      }
    >
      <div className="editor-pane">
        {!sidebarOpen ? (
          <button
            type="button"
            className="sidebar-reopen"
            title={t('wiki.expandSidebar')}
            aria-label={t('wiki.expandSidebar')}
            onClick={toggleSidebar}
          >
            »
          </button>
        ) : null}
        <div className="editor-scroll">
          <div className="editor-column">
            <div className="editor-toolbar">
              <input
                className="title-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={() => saveTitle(title.trim() || t('wiki.untitled'))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.currentTarget.blur()
                  }
                }}
              />
              <span className="save-hint">{saveHint}</span>
            </div>
            {error ? <p className="error">{error}</p> : null}
            <BlockEditor
              ref={editorRef}
              key={`${page.id}:${locale}`}
              pageId={page.id}
              initialBody={page.body || '[]'}
              onChange={saveBody}
            />
          </div>
        </div>
      </div>
      {toast ? (
        <div className="save-toast" role="status" aria-live="polite">
          {toast}
        </div>
      ) : null}
      <ProjectModal
        open={editProjectOpen}
        mode="edit"
        initial={project}
        busy={busy}
        onClose={() => setEditProjectOpen(false)}
        onSubmit={onEditProject}
      />
      <ProjectModal
        open={createProjectOpen}
        mode="create"
        busy={busy}
        onClose={() => setCreateProjectOpen(false)}
        onSubmit={onCreateProject}
      />
    </Shell>
  )
}
