import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createProject,
  listProjects,
  type WikiProject,
} from '../api/wiki'
import { ProjectModal } from '../components/ProjectModal'
import { Shell } from '../components/Shell'
import { useI18n } from '../useI18n'

export function ProjectListPage() {
  const navigate = useNavigate()
  const { t } = useI18n()
  const [items, setItems] = useState<WikiProject[]>([])
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function refresh() {
    const res = await listProjects()
    setItems(res.items)
  }

  useEffect(() => {
    refresh().catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function onCreate(values: { name: string; description: string }) {
    setBusy(true)
    setError('')
    try {
      const res = await createProject(values)
      setModalOpen(false)
      const home = res.home_page?.id || res.project.home_page_id
      if (home) navigate(`/${home}`)
      else await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell>
      <section className="project-list">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'end' }}>
          <div>
            <h1>{t('wiki.projects')}</h1>
            <p className="lead">{t('wiki.projectsLead')}</p>
          </div>
          <button type="button" className="btn primary" onClick={() => setModalOpen(true)}>
            {t('wiki.newProject')}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {!items.length ? (
          <div className="empty">
            <p>{t('wiki.noProjects')}</p>
            <button type="button" className="btn primary" onClick={() => setModalOpen(true)}>
              {t('wiki.createFirst')}
            </button>
          </div>
        ) : (
          <div className="project-grid">
            {items.map((p) => (
              <button
                key={p.id}
                type="button"
                className="project-card"
                onClick={() => {
                  if (p.home_page_id) navigate(`/${p.home_page_id}`)
                }}
              >
                <h2>{p.name}</h2>
                <p>{p.description || t('wiki.noDescription')}</p>
                <div className="meta">
                  <span className="lead" style={{ margin: 0 }}>
                    {t('wiki.open')}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>
      <ProjectModal
        open={modalOpen}
        mode="create"
        busy={busy}
        error={error}
        onClose={() => setModalOpen(false)}
        onSubmit={onCreate}
      />
    </Shell>
  )
}
