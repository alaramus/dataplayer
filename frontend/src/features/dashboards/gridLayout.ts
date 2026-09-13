/**
 * The arithmetic of the dashboard grid, free of Vue and the DOM.
 *
 * Twelve columns and rows of one height. Nothing floats: a widget moved or
 * resized onto another pushes it down, and then everything falls up as far as
 * it can. The limits mirror `app/metrics/dashboards.py`, which refuses a layout
 * outside them.
 */

export const GRID_COLUMNS = 12
export const MIN_W = 2
export const MIN_H = 2
export const MAX_H = 40
export const MAX_Y = 400

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

export interface Placed {
  id: string
  layout: Box
}

export function clampBox(box: Box): Box {
  const w = Math.min(GRID_COLUMNS, Math.max(MIN_W, Math.round(box.w)))
  const h = Math.min(MAX_H, Math.max(MIN_H, Math.round(box.h)))
  const x = Math.min(GRID_COLUMNS - w, Math.max(0, Math.round(box.x)))
  const y = Math.min(MAX_Y, Math.max(0, Math.round(box.y)))
  return { x, y, w, h }
}

export function overlaps(a: Box, b: Box): boolean {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h
}

function byPosition(a: Placed, b: Placed): number {
  return a.layout.y - b.layout.y || a.layout.x - b.layout.x
}

/** Every widget as high as it can go, in reading order. */
export function compact(items: readonly Placed[]): Placed[] {
  const settled: Placed[] = []
  for (const item of [...items].sort(byPosition)) {
    let box = { ...item.layout }
    while (box.y > 0 && !settled.some((other) => overlaps({ ...box, y: box.y - 1 }, other.layout))) {
      box = { ...box, y: box.y - 1 }
    }
    settled.push({ id: item.id, layout: box })
  }
  return keepOrder(items, settled)
}

/** Put one widget where it was asked to go and make room for it. */
export function moveItem(items: readonly Placed[], id: string, to: { x: number; y: number }): Placed[] {
  return settleAround(items, id, (box) => clampBox({ ...box, x: to.x, y: to.y }))
}

export function resizeItem(items: readonly Placed[], id: string, size: { w: number; h: number }): Placed[] {
  return settleAround(items, id, (box) => clampBox({ ...box, w: size.w, h: size.h }))
}

/** The first place, reading top to bottom and left to right, a box fits. */
export function findFreeSpot(items: readonly Placed[], w: number, h: number): { x: number; y: number } {
  const width = Math.min(GRID_COLUMNS, Math.max(MIN_W, w))
  for (let y = 0; y <= MAX_Y; y += 1) {
    for (let x = 0; x + width <= GRID_COLUMNS; x += 1) {
      const box = { x, y, w: width, h }
      if (!items.some((item) => overlaps(box, item.layout))) return { x, y }
    }
  }
  return { x: 0, y: gridRows(items) }
}

/** How many rows the widgets take. */
export function gridRows(items: readonly Placed[]): number {
  return items.reduce((rows, item) => Math.max(rows, item.layout.y + item.layout.h), 0)
}

function settleAround(
  items: readonly Placed[],
  id: string,
  change: (box: Box) => Box
): Placed[] {
  const target = items.find((item) => item.id === id)
  if (target === undefined) return [...items]
  const fixed: Placed = { id, layout: change(target.layout) }
  const settled: Placed[] = [fixed]
  const others = items.filter((item) => item.id !== id).sort(byPosition)
  for (const item of others) {
    let box = { ...item.layout }
    let pushed = true
    while (pushed) {
      pushed = false
      for (const other of settled) {
        if (overlaps(box, other.layout)) {
          box = { ...box, y: other.layout.y + other.layout.h }
          pushed = true
        }
      }
    }
    settled.push({ id: item.id, layout: box })
  }
  return compact(keepOrder(items, settled))
}

/** The caller's order, with the new boxes: a widget list is not re-sorted by moving one. */
function keepOrder(original: readonly Placed[], placed: readonly Placed[]): Placed[] {
  const byId = new Map(placed.map((item) => [item.id, item]))
  return original.map((item) => byId.get(item.id) ?? item)
}
