export type IconName =
  | 'chevrons-left'
  | 'chevrons-right'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-down'
  | 'columns'
  | 'filter'
  | 'refresh'
  | 'sort'
  | 'sort-asc'
  | 'sort-desc'
  | 'calendar'
  | 'check'

export interface IconMark {
  d?: string
  circle?: { cx: number; cy: number; r: number }
  sw: number
  cap?: boolean
  join?: boolean
}

/** 16×16 描边图标。线宽按原来各处内联 svg 保留。 */
export const ICONS: Record<IconName, IconMark[]> = {
  'chevrons-left': [
    {
      d: 'M12.5 3.5 8 8l4.5 4.5M7.5 3.5 3 8l4.5 4.5',
      sw: 1.6,
      cap: true,
      join: true,
    },
  ],
  'chevrons-right': [
    {
      d: 'M3.5 3.5 8 8l-4.5 4.5M8.5 3.5 13 8l-4.5 4.5',
      sw: 1.6,
      cap: true,
      join: true,
    },
  ],
  'chevron-left': [
    { d: 'M10 3.5 5.5 8 10 12.5', sw: 1.6, cap: true, join: true },
  ],
  'chevron-right': [
    { d: 'M6 3.5 10.5 8 6 12.5', sw: 1.6, cap: true, join: true },
  ],
  'chevron-down': [
    { d: 'M4 6l4 4 4-4', sw: 1.5, cap: true, join: true },
  ],
  columns: [
    { circle: { cx: 8, cy: 8, r: 2.1 }, sw: 1.4 },
    {
      d: 'M8 1.6v2.1M8 12.3v2.1M1.6 8h2.1M12.3 8h2.1M3.3 3.3l1.5 1.5M11.2 11.2l1.5 1.5M12.7 3.3 11.2 4.8M4.8 11.2 3.3 12.7',
      sw: 1.4,
      cap: true,
    },
  ],
  filter: [
    { d: 'M2.5 3.5h11l-4 4.5V13l-3-1.5V8L2.5 3.5z', sw: 1.4, join: true },
  ],
  refresh: [
    { d: 'M13.5 8a5.5 5.5 0 1 1-1.3-3.6', sw: 1.5, cap: true },
    { d: 'M13.5 3.2v3.1h-3.1', sw: 1.5, cap: true, join: true },
  ],
  sort: [
    { d: 'M5 6l3-3 3 3M5 10l3 3 3-3', sw: 1.4, cap: true, join: true },
  ],
  'sort-asc': [
    { d: 'M8 3v10M8 3l3.5 3.5M8 3L4.5 6.5', sw: 1.6, cap: true, join: true },
  ],
  'sort-desc': [
    { d: 'M8 13V3M8 13l3.5-3.5M8 13L4.5 9.5', sw: 1.6, cap: true, join: true },
  ],
  calendar: [
    {
      d: 'M3 5h10v8H3zM3 7h10M5 3.5v2M11 3.5v2',
      sw: 1.2,
      cap: true,
      join: true,
    },
  ],
  check: [{ d: 'M3.5 8.5l3 3 6-6.5', sw: 2, cap: true, join: true }],
}
