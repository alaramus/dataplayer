/**
 * Which part of a page is drawn: the rows and columns in view, a few beyond
 * them, and a measured gap standing in for the rest.
 *
 * Pure arithmetic over sizes the grid already knows. Rows are one text line
 * each (D24), so one measured height places every row; columns carry their
 * own widths. Pinned columns are always drawn and are not part of the window.
 */

/** A run of drawn items and the room left for those that are not drawn. */
export interface VirtualWindow {
  /** First drawn index. */
  start: number
  /** One past the last drawn index. */
  end: number
  /** Pixels standing in for the items before `start`. */
  before: number
  /** Pixels standing in for the items from `end` on. */
  after: number
}

export const ROW_OVERSCAN = 10
export const COLUMN_OVERSCAN = 3

/**
 * The rows that cross the stretch from `offset` to `offset + span`.
 *
 * `offset` is how far the body is scrolled past its own top; a span longer
 * than the viewport costs a few rows and never hides one.
 */
export function rowWindow(
  count: number,
  rowHeight: number,
  offset: number,
  span: number,
  overscan = ROW_OVERSCAN
): VirtualWindow {
  if (count <= 0 || rowHeight <= 0) return { start: 0, end: Math.max(0, count), before: 0, after: 0 }
  const first = Math.floor(Math.max(0, offset) / rowHeight)
  const last = Math.ceil((Math.max(0, offset) + Math.max(0, span)) / rowHeight)
  const { start, end } = snapped(first, last, overscan, count)
  return { start, end, before: start * rowHeight, after: (count - end) * rowHeight }
}

/** The columns, by their widths in display order, that cross the same kind of stretch. */
export function columnWindow(
  widths: readonly number[],
  offset: number,
  span: number,
  overscan = COLUMN_OVERSCAN
): VirtualWindow {
  const from = Math.max(0, offset)
  const to = from + Math.max(0, span)
  let position = 0
  let first = widths.length
  let last = widths.length
  for (let index = 0; index < widths.length; index += 1) {
    const width = widths[index] ?? 0
    if (first === widths.length && position + width > from) first = index
    if (position >= to) {
      last = index
      break
    }
    position += width
  }
  const { start, end } = snapped(first, last, overscan, widths.length)
  return {
    start,
    end,
    before: sum(widths, 0, start),
    after: sum(widths, end, widths.length),
  }
}

/**
 * Where a scrolled box has to move so that a stretch inside it is in view.
 *
 * `reserved` is the part of the viewport that something stuck to its start
 * covers — the heading above the rows, the selector and pinned columns beside
 * them — so an item scrolled under it counts as hidden. Returns the position
 * unchanged when the stretch already shows.
 */
export function revealOffset(
  current: number,
  viewport: number,
  reserved: number,
  itemStart: number,
  itemSize: number
): number {
  const visibleStart = current + reserved
  const visibleEnd = current + viewport
  if (itemStart < visibleStart) return Math.max(0, itemStart - reserved)
  if (itemStart + itemSize > visibleEnd) {
    return Math.max(0, Math.min(itemStart - reserved, itemStart + itemSize - viewport))
  }
  return current
}

/**
 * At least `overscan` items beyond each edge of what shows, with both ends
 * moved out to a multiple of `overscan`.
 *
 * Without the second half every row scrolled past was a new window and a
 * redraw of every drawn cell; with it the window stays put for `overscan`
 * items at a time, and most frames of a scroll redraw nothing.
 */
function snapped(
  first: number,
  last: number,
  overscan: number,
  count: number
): { start: number; end: number } {
  const step = Math.max(1, overscan)
  const start = clamp(Math.floor((first - overscan) / step) * step, 0, count)
  const end = clamp(Math.ceil((last + overscan) / step) * step, start, count)
  return { start, end }
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value))
}

function sum(values: readonly number[], from: number, to: number): number {
  let total = 0
  for (let index = from; index < to; index += 1) total += values[index] ?? 0
  return total
}
