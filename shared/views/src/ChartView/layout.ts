import type { ChartLayout } from './types'

/** 把 charts.json 的格子坐标换成网格样式。 */
export function chartSlotStyle(layout?: ChartLayout): Record<string, string> {
  const { x, y, w, h } = layout || { x: 0, y: 0, w: 6, h: 4 }
  return {
    gridColumn: `${x + 1} / span ${Math.max(w, 1)}`,
    gridRow: `${y + 1} / span ${Math.max(h, 1)}`,
  }
}
