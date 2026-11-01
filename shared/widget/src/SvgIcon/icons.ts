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
  | 'agent'
  | 'bell'
  | 'shield'
  | 'building'
  | 'search'

export interface IconMark {
  d?: string
  circle?: { cx: number; cy: number; r: number }
  sw: number
  cap?: boolean
  join?: boolean
  fill?: boolean
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
  agent: [
    { d: 'M8 1.8v1.5', sw: 1.4, cap: true },
    { d: 'M5.3 4.6V3.8a2.7 2.7 0 0 1 5.4 0v.8', sw: 1.4, cap: true, join: true },
    {
      d: 'M3.2 5.2h9.6a1.2 1.2 0 0 1 1.2 1.2v5.1a1.2 1.2 0 0 1-1.2 1.2H3.2A1.2 1.2 0 0 1 2 11.5V6.4a1.2 1.2 0 0 1 1.2-1.2z',
      sw: 1.4,
      join: true,
    },
    { circle: { cx: 6.1, cy: 8.6, r: 0.7 }, sw: 0, fill: true },
    { circle: { cx: 9.9, cy: 8.6, r: 0.7 }, sw: 0, fill: true },
    { d: 'M5.2 12.8v1.4M10.8 12.8v1.4', sw: 1.4, cap: true },
  ],
  bell: [
    {
      d: 'M3.6 6.1a4.4 4.4 0 0 1 8.8 0c0 2.2.9 3.3 1.5 4.2H2.1c.6-.9 1.5-2 1.5-4.2',
      sw: 1.4,
      cap: true,
      join: true,
    },
    { d: 'M6.5 12.4a1.5 1.5 0 0 0 3 0', sw: 1.4, cap: true, join: true },
  ],
  shield: [
    {
      d: 'M8 1.5 13.2 3.6v4.1c0 2.9-2 5.1-5.2 6.2C4.8 12.8 2.8 10.6 2.8 7.7V3.6L8 1.5z',
      sw: 1.4,
      join: true,
    },
    { d: 'M5.8 8.1 7.3 9.6l3-3', sw: 1.4, cap: true, join: true },
  ],
  building: [
    { d: 'M2 14.2h12', sw: 1.4, cap: true },
    { d: 'M3.3 14.2V5.2L8 2.4l4.7 2.8v9', sw: 1.4, cap: true, join: true },
    { d: 'M6 14.2V10h4v4.2', sw: 1.4, cap: true, join: true },
  ],
  search: [
    { circle: { cx: 7, cy: 7, r: 4.2 }, sw: 1.5 },
    { d: 'M10.2 10.2 14 14', sw: 1.6, cap: true },
  ],
}
