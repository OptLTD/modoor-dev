import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react'
import {
  BlockNoteSchema,
  defaultBlockSpecs,
  filterSuggestionItems,
  insertOrUpdateBlock,
  type BlockNoteEditor,
} from '@blocknote/core'
import { en, zh } from '@blocknote/core/locales'
import { BlockNoteView } from '@blocknote/mantine'
import {
  createReactBlockSpec,
  getDefaultReactSlashMenuItems,
  SuggestionMenuController,
  useCreateBlockNote,
  type DefaultReactSuggestionItem,
} from '@blocknote/react'
import { Extension, InputRule } from '@tiptap/core'
import type { Block } from '@blocknote/core'
import { WikiSlashMenu } from './WikiSlashMenu'
import { useI18n } from '../useI18n'
import '@blocknote/core/fonts/inter.css'
import '@blocknote/mantine/style.css'

type Props = {
  pageId: string
  initialBody: string
  onChange: (json: string) => void
}

export type BlockEditorHandle = {
  /** Cancel debounced autosave and return current document JSON */
  flush: () => string
}

const Divider = createReactBlockSpec(
  {
    type: 'divider',
    propSchema: {},
    content: 'none',
  },
  {
    render: () => (
      <div className="wiki-divider" contentEditable={false}>
        <hr />
      </div>
    ),
    parse: (el) => {
      if (el.tagName === 'HR' || el.classList.contains('wiki-divider')) return {}
      return undefined
    },
    toExternalHTML: () => <hr />,
  },
)

const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    divider: Divider,
  },
})

const HIDDEN_SLASH_TITLES = new Set(['视频', '音频', '文件', '表情', 'Video', 'Audio', 'File', 'Emoji'])

function DividerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 12h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function TodoIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7.5 12.5l3 3 6-7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

type Labels = {
  placeholder: string
  divider: string
  dividerSub: string
  todo: string
  todoSub: string
  groupBasic: string
  groupHeading: string
  groupInsert: string
}

function buildDictionary(locale: string, labels: Labels) {
  const base = locale.startsWith('zh') ? zh : en
  return {
    ...base,
    placeholders: {
      ...base.placeholders,
      default: labels.placeholder,
      emptyDocument: labels.placeholder,
    },
    slash_menu: {
      ...base.slash_menu,
      heading: { ...base.slash_menu.heading, group: labels.groupHeading },
      heading_2: { ...base.slash_menu.heading_2, group: labels.groupHeading },
      heading_3: { ...base.slash_menu.heading_3, group: labels.groupHeading },
      quote: { ...base.slash_menu.quote, group: labels.groupBasic },
      numbered_list: { ...base.slash_menu.numbered_list, group: labels.groupBasic },
      bullet_list: { ...base.slash_menu.bullet_list, group: labels.groupBasic },
      check_list: {
        ...base.slash_menu.check_list,
        title: labels.todo,
        subtext: labels.todoSub,
        aliases: ['todo', 'task', 'checklist', '待办', '任务', '勾选', '[]', '[ ]'],
        group: labels.groupBasic,
      },
      paragraph: { ...base.slash_menu.paragraph, group: labels.groupBasic },
      code_block: { ...base.slash_menu.code_block, group: labels.groupBasic },
      table: { ...base.slash_menu.table, group: labels.groupInsert },
      image: { ...base.slash_menu.image, group: labels.groupInsert },
    },
  }
}

function insertDividerItem(
  editor: BlockNoteEditor<typeof schema.blockSchema>,
  labels: Labels,
): DefaultReactSuggestionItem {
  return {
    title: labels.divider,
    subtext: labels.dividerSub,
    aliases: ['hr', 'divider', 'separator', '---', '分隔线', '分割线'],
    group: labels.groupBasic,
    icon: <DividerIcon />,
    onItemClick: () => {
      insertOrUpdateBlock(editor, { type: 'divider' })
    },
  }
}

function getWikiSlashMenuItems(
  editor: BlockNoteEditor<typeof schema.blockSchema>,
  labels: Labels,
): DefaultReactSuggestionItem[] {
  const defaults: DefaultReactSuggestionItem[] = getDefaultReactSlashMenuItems(editor)
    .filter((item) => !HIDDEN_SLASH_TITLES.has(item.title))
    .map((item) => {
      const { badge: _badge, ...rest } = item
      if (
        rest.title === labels.todo ||
        rest.title === '待办' ||
        rest.title === '检查清单' ||
        rest.title === 'Check List' ||
        rest.title === 'To-do' ||
        rest.title === 'Todo'
      ) {
        return {
          ...rest,
          title: labels.todo,
          subtext: labels.todoSub,
          icon: <TodoIcon />,
          aliases: ['todo', 'task', 'checklist', '待办', '任务', '勾选', '[]', '[ ]'],
          group: labels.groupBasic,
        }
      }
      return rest
    })

  const divider = insertDividerItem(editor, labels)
  const basic = defaults.filter(
    (i) =>
      i.group === labels.groupBasic ||
      i.group === '基础' ||
      i.group === 'Basic blocks' ||
      i.group === 'Basic' ||
      i.group === '基本块',
  )
  const headings = defaults.filter(
    (i) => i.group === labels.groupHeading || i.group === '标题' || i.group === 'Headings',
  )
  const insert = defaults.filter(
    (i) =>
      i.group === labels.groupInsert ||
      i.group === '插入' ||
      i.group === '媒体' ||
      i.group === '高级功能' ||
      i.group === 'Advanced' ||
      i.group === 'Media',
  )
  const rest = defaults.filter(
    (i) => !basic.includes(i) && !headings.includes(i) && !insert.includes(i),
  )

  const withDivider = [...basic]
  const todoIdx = withDivider.findIndex((i) => i.title === labels.todo)
  if (todoIdx >= 0) withDivider.splice(todoIdx + 1, 0, divider)
  else withDivider.push(divider)

  return [...withDivider, ...headings, ...insert, ...rest]
}

function createDividerShortcut(getEditor: () => BlockNoteEditor<typeof schema.blockSchema> | null) {
  return Extension.create({
    name: 'wikiDividerShortcut',
    addInputRules() {
      return [
        new InputRule({
          find: /^-{3}$/,
          handler: ({ range, chain }) => {
            chain().deleteRange({ from: range.from, to: range.to }).run()
            const editor = getEditor()
            if (editor) insertOrUpdateBlock(editor, { type: 'divider' })
          },
        }),
        new InputRule({
          find: /^-{3}\s$/,
          handler: ({ range, chain }) => {
            chain().deleteRange({ from: range.from, to: range.to }).run()
            const editor = getEditor()
            if (editor) insertOrUpdateBlock(editor, { type: 'divider' })
          },
        }),
      ]
    },
  })
}

function parseBlocks(raw: string): Block[] | undefined {
  try {
    const data = JSON.parse(raw || '[]')
    if (Array.isArray(data) && data.length) return data as Block[]
  } catch {
    /* empty */
  }
  return undefined
}

export const BlockEditor = forwardRef<BlockEditorHandle, Props>(function BlockEditor(
  { pageId, initialBody, onChange },
  ref,
) {
  const { t, locale } = useI18n()
  const labels = useMemo<Labels>(
    () => ({
      placeholder: t('wiki.editorPlaceholder'),
      divider: t('wiki.divider'),
      dividerSub: t('wiki.dividerSub'),
      todo: t('wiki.todo'),
      todoSub: t('wiki.todoSub'),
      groupBasic: t('wiki.groupBasic'),
      groupHeading: t('wiki.groupHeading'),
      groupInsert: t('wiki.groupInsert'),
    }),
    [t, locale],
  )
  const dictionary = useMemo(() => buildDictionary(String(locale), labels), [locale, labels])
  const initial = useMemo(() => parseBlocks(initialBody), [pageId]) // eslint-disable-line react-hooks/exhaustive-deps
  const editorRef = useRef<BlockNoteEditor<typeof schema.blockSchema> | null>(null)

  const editor = useCreateBlockNote({
    schema,
    dictionary,
    initialContent: initial,
    _tiptapOptions: {
      extensions: [createDividerShortcut(() => editorRef.current)],
    },
  })

  editorRef.current = editor

  const timer = useRef<number | null>(null)
  const ready = useRef(false)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useImperativeHandle(ref, () => ({
    flush: () => {
      if (timer.current) {
        window.clearTimeout(timer.current)
        timer.current = null
      }
      return JSON.stringify(editor.document)
    },
  }))

  useEffect(() => {
    ready.current = false
    const readyTimer = window.setTimeout(() => {
      ready.current = true
    }, 300)
    return () => window.clearTimeout(readyTimer)
  }, [pageId])

  return (
    <div className="editor-body">
      <BlockNoteView
        editor={editor}
        theme="light"
        slashMenu={false}
        onChange={() => {
          if (!ready.current) return
          if (timer.current) window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => {
            onChangeRef.current(JSON.stringify(editor.document))
          }, 800)
        }}
      >
        <SuggestionMenuController
          triggerCharacter="/"
          suggestionMenuComponent={WikiSlashMenu}
          getItems={async (query) =>
            filterSuggestionItems(getWikiSlashMenuItems(editor, labels), query)
          }
        />
      </BlockNoteView>
    </div>
  )
})
