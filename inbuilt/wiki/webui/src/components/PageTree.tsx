import { useEffect, useRef, useState } from 'react'
import type { DragEvent, MutableRefObject } from 'react'
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

type DropPlace = 'before' | 'after' | 'inside'
type DragState = { id: string; home: boolean }

function dropPlace(event: DragEvent<HTMLElement>, homeDrag: boolean): DropPlace {
  const rect = event.currentTarget.getBoundingClientRect()
  const ratio = rect.height ? (event.clientY - rect.top) / rect.height : 0.5
  if (homeDrag) return ratio < 0.5 ? 'before' : 'after'
  if (ratio < 0.38) return 'before'
  if (ratio > 0.62) return 'after'
  return 'inside'
}

function siblingIndex(siblings: TreeNode[], draggedId: string, targetId: string, after: boolean) {
  const ids = siblings.map((item) => item.id).filter((id) => id !== draggedId)
  let index = ids.indexOf(targetId)
  if (index < 0) index = ids.length
  return after ? index + 1 : index
}

function NodeRow({
  node,
  depth,
  siblings,
  activeId,
  homePageId,
  dragRef,
  onSelect,
  onAddChild,
  onDelete,
  onMove,
}: {
  node: TreeNode
  depth: number
  siblings: TreeNode[]
  activeId: string
  homePageId?: string | null
  dragRef: MutableRefObject<DragState | null>
  onSelect: (id: string) => void
  onAddChild: (parentId: string | null) => void
  onDelete: (id: string) => void
  onMove: (id: string, parentId: string | null, sortOrder: number) => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const [hint, setHint] = useState<DropPlace | ''>('')
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
        className={`tree-item ${activeId === node.id ? 'active' : ''}${menuOpen ? ' menu-open' : ''}${hint ? ` drop-${hint}` : ''}`}
        style={{ paddingLeft: 6 + depth * 4 }}
        role="treeitem"
        aria-label={node.title}
        draggable
        onDragStart={(e) => {
          dragRef.current = { id: node.id, home: isHome }
          e.dataTransfer.setData('text/page-id', node.id)
          e.dataTransfer.effectAllowed = 'move'
        }}
        onDragEnd={() => {
          dragRef.current = null
          setHint('')
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.stopPropagation()
          e.dataTransfer.dropEffect = 'move'
          const dragged = dragRef.current
          if (!dragged || dragged.id === node.id) {
            setHint('')
            return
          }
          const place = dropPlace(e, dragged.home)
          if (dragged.home && place !== 'inside' && node.parent_id) {
            setHint('')
            return
          }
          setHint(place)
        }}
        onDragLeave={(e) => {
          const next = e.relatedTarget
          if (next instanceof Node && e.currentTarget.contains(next)) return
          setHint('')
        }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          const dragged = e.dataTransfer.getData('text/page-id') || dragRef.current?.id || ''
          const homeDrag = dragRef.current?.home || dragged === homePageId
          setHint('')
          if (!dragged || dragged === node.id) return
          const place = dropPlace(e, Boolean(homeDrag))
          if (place === 'inside') {
            onMove(dragged, node.id, 0)
            return
          }
          if (homeDrag && node.parent_id) return
          onMove(dragged, node.parent_id, siblingIndex(siblings, dragged, node.id, place === 'after'))
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
        {hint ? (
          <span className="tree-drop-label">
            {hint === 'before' ? t('wiki.dropBefore') : hint === 'after' ? t('wiki.dropAfter') : t('wiki.dropInside')}
          </span>
        ) : null}
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
              siblings={node.children}
              activeId={activeId}
              homePageId={homePageId}
              dragRef={dragRef}
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
  const dragRef = useRef<DragState | null>(null)
  return (
    <div
      className="tree"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault()
        const dragged = e.dataTransfer.getData('text/page-id') || dragRef.current?.id || ''
        if (!dragged) return
        const ids = props.tree.map((node) => node.id).filter((id) => id !== dragged)
        props.onMove(dragged, null, ids.length)
      }}
    >
      {props.tree.map((node) => (
        <NodeRow
          key={node.id}
          node={node}
          depth={0}
          siblings={props.tree}
          dragRef={dragRef}
          activeId={props.activeId}
          homePageId={props.homePageId}
          onSelect={props.onSelect}
          onAddChild={props.onAddChild}
          onDelete={props.onDelete}
          onMove={props.onMove}
        />
      ))}
    </div>
  )
}
