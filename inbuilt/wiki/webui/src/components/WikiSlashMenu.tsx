import type { DefaultReactSuggestionItem, SuggestionMenuProps } from '@blocknote/react'
import { useI18n } from '../useI18n'

export function WikiSlashMenu(props: SuggestionMenuProps<DefaultReactSuggestionItem>) {
  const { items, loadingState, selectedIndex, onItemClick } = props
  const { t } = useI18n()

  if (loadingState === 'loading-initial' || (loadingState === 'loading' && items.length === 0)) {
    return <div className="wiki-slash-menu wiki-slash-menu--loading">{t('wiki.slashLoading')}</div>
  }

  if (items.length === 0) {
    return <div className="wiki-slash-menu wiki-slash-menu--empty">{t('wiki.slashEmpty')}</div>
  }

  let currentGroup: string | undefined

  return (
    <div className="wiki-slash-menu" role="listbox">
      {items.map((item, index) => {
        const showGroup = item.group !== currentGroup
        if (showGroup) currentGroup = item.group
        const selected = index === selectedIndex
        return (
          <div key={`${item.group}-${item.title}`}>
            {showGroup && currentGroup ? (
              <div className="wiki-slash-group">{currentGroup}</div>
            ) : null}
            <button
              type="button"
              role="option"
              className={`wiki-slash-item${selected ? ' is-selected' : ''}`}
              aria-selected={selected}
              id={`bn-suggestion-menu-item-${index}`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onItemClick?.(item)}
            >
              {item.icon ? <span className="wiki-slash-icon">{item.icon}</span> : null}
              <span className="wiki-slash-text">
                <span className="wiki-slash-title">{item.title}</span>
                {item.subtext ? <span className="wiki-slash-sub">{item.subtext}</span> : null}
              </span>
            </button>
          </div>
        )
      })}
    </div>
  )
}
