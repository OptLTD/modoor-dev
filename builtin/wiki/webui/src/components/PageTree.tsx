import { useEffect, useRef, useState } from 'react'
import type { TreeNode } from '../api/wiki'
import { useI18n } from '../useI18n'

type Props = {
  tree: TreeNode[]
  activeId: string
  homePageId?: string | null
  onSelect: (id: string) => void
  onAddChild: (parentId: string | null) => void
  onDelete: (id: string) => void
  onMove: (id: string, parentId: string | null, sortOrder: number) => void
}

function NodeRow({
  node,
  depth,
  activeId,
  homePageId,
  onSelect,
  onAddChild,
  onDelete,
  onMove,
}: {
  node: TreeNode
  depth: number
  activeId: string
  homePageId?: string | null
  onSelect: (id: string) => void
  onAddChild: (parentId: string | null) => void
  onDelete: (id: string) => void
  onMove: (id: string, parentId: string | null, sortOrder: number) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const isHome = homePageId === node.id

  useEffect(() => {
    if (!menuOpen) return
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  return (
    <div>
      <div
        className={`tree-item ${activeId === node.id ? 'active' : ''}${menuOpen ? ' menu-open' : ''}`}
        style={{ paddingLeft: 6 + depth * 4 }}
        draggable={!isHome}
        onDragStart={(e) => {
          e.dataTransfer.setData('text/page-id', node.id)
          e.dataTransfer.effectAllowed = 'move'
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
        }}
        onDrop={(e) => {
          e.preventDefault()
          const dragged = e.dataTransfer.getData('text/page-id')
          if (!dragged || dragged === node.id) return
          onMove(dragged, node.id, 0)
        }}
        onClick={() => onSelect(node.id)}
      >
        {node.children.length ? (
          <button
            type="button"
            className="icon-btn"
            onClick={(e) => {
              e.stopPropagation()
              setOpen((v) => !v)
            }}
          >
            {open ? '▾' : '▸'}
          </button>
        ) : (
          <span className="icon-btn">·</span>
        )}
        <span className="title">{node.title}</span>
        <div
          className="tree-item-menu"
          ref={menuRef}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="icon-btn menu-trigger"
            title={t('wiki.more')}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            ⋯
          </button>
          {menuOpen ? (
            <div className="tree-item-dropdown" role="menu">
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false)
                  onAddChild(node.id)
                }}
              >
                {t('wiki.newChild')}
              </button>
              {!isHome ? (
                <button
                  type="button"
                  role="menuitem"
                  className="danger"
                  onClick={() => {
                    setMenuOpen(false)
                    onDelete(node.id)
                  }}
                >
                  {t('wiki.delete')}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      {open && node.children.length ? (
        <div className="tree-children">
          {node.children.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              activeId={activeId}
              homePageId={homePageId}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onDelete={onDelete}
              onMove={onMove}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function PageTree(props: Props) {
  return (
    <div
      className="tree"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        const dragged = e.dataTransfer.getData('text/page-id')
        if (dragged) props.onMove(dragged, null, 0)
      }}
    >
      {props.tree.map((node) => (
        <NodeRow key={node.id} node={node} depth={0} {...props} />
      ))}
    </div>
  )
}
