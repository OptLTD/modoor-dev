import { FormEvent, useEffect, useState } from 'react'
import type { WikiProject } from '../api/wiki'
import { useI18n } from '../useI18n'

type Props = {
  open: boolean
  mode: 'create' | 'edit'
  initial?: Pick<WikiProject, 'name' | 'description'> | null
  busy?: boolean
  error?: string
  onClose: () => void
  onSubmit: (values: { name: string; description: string }) => void | Promise<void>
}

export function ProjectModal({
  open,
  mode,
  initial,
  busy,
  error,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useI18n()
  const [name, setName] = useState(initial?.name || '')
  const [description, setDescription] = useState(initial?.description || '')

  useEffect(() => {
    if (open) {
      setName(initial?.name || '')
      setDescription(initial?.description || '')
    }
  }, [open, initial?.name, initial?.description])

  if (!open) return null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    await onSubmit({ name: name.trim(), description: description.trim() })
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h3>{mode === 'create' ? t('wiki.newProject') : t('wiki.editProject')}</h3>
        <label htmlFor="wiki-project-name">{t('wiki.name')}</label>
        <input
          id="wiki-project-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
          placeholder={t('wiki.namePh')}
        />
        <label htmlFor="wiki-project-desc">{t('wiki.description')}</label>
        <textarea
          id="wiki-project-desc"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('wiki.optional')}
        />
        {error ? <p className="error">{error}</p> : null}
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            {t('wiki.cancel')}
          </button>
          <button type="submit" className="btn primary" disabled={busy || !name.trim()}>
            {busy ? t('wiki.saving') : t('wiki.save')}
          </button>
        </div>
      </form>
    </div>
  )
}
