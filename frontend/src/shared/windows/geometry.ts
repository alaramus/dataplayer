/**
 * Where a floating window sits, and in what order windows stack.
 *
 * Plain functions with no imports, so the rules are checked without mounting
 * anything — the way `tree.ts` and `placement.ts` are for the workspace. The
 * old application's window manager mutated geometry in place inside the
 * manager itself, which left nothing to test and nothing to reason about.
 */

export interface Size {
  width: number
  height: number
}

export interface Rect extends Size {
  x: number
  y: number
}

export type ResizeEdge =
  | "top"
  | "right"
  | "bottom"
  | "left"
  | "top-left"
  | "top-right"
  | "bottom-left"
  | "bottom-right"

/** How far each new window is offset from the one before it. */
export const CASCADE_STEP = 32

/**
 * How much of a window must stay on screen.
 *
 * Not the whole window: dragging one partly past an edge is ordinary and
 * useful. What must never leave is enough of the title bar to grab it by —
 * the old engine clamped nothing at all, so a window pushed past the right
 * edge could not be brought back by any means.
 */
export const GRAB_MARGIN = 120

/**
 * How much shorter than the viewport a content-sized window may be.
 *
 * A viewport-tall window fits only at y=0, which makes an ordinary drag a way
 * to lose its footer immediately. The store keeps the margin when it measures
 * content, and the frame keeps it when it draws itself: with `height: auto`
 * the drawn box is the content's, and nothing else would stop it.
 */
export const FIT_MARGIN = 16

/**
 * Where the cascade begins: the middle of the viewport.
 *
 * Not the top left, which is where this started and where it was wrong. A
 * window opening at the corner lands on top of the column it was opened from
 * and covers the very control that opens the next one — and opening a second
 * window beside the first is the whole reason these are not modal.
 *
 * The middle is a rule the engine can state without knowing what is on the
 * screen behind it, which is the only kind of rule it is allowed to have.
 */
function origin(size: Size, viewport: Size): { x: number; y: number } {
  return {
    x: Math.round((viewport.width - size.width) / 2),
    y: Math.round((viewport.height - size.height) / 2),
  }
}

function bounded(value: number, low: number, high: number): number {
  // low wins when the range is inverted, which happens when the viewport is
  // narrower than the margin it is asked to keep.
  return Math.max(low, Math.min(high, value))
}

/**
 * Keep a window reachable.
 *
 * The top edge is treated differently from the other three: a window pushed
 * up loses the very strip it is dragged by, so it is stopped at zero instead
 * of being allowed a margin's worth of overhang.
 */
export function clamp(rect: Rect, viewport: Size): Rect {
  return {
    ...rect,
    x: bounded(rect.x, GRAB_MARGIN - rect.width, viewport.width - GRAB_MARGIN),
    y: bounded(rect.y, 0, viewport.height - GRAB_MARGIN),
  }
}

/**
 * Where to put a window that is being opened.
 *
 * Offset from the last one opened rather than from the number of open
 * windows: closing one in the middle would otherwise send the next new window
 * backwards, onto a place that is still taken.
 *
 * The cascade restarts once it would walk off the screen, so a long session
 * does not push windows out of reach before `clamp` has to rescue them.
 */
export function place(size: Size, previous: Rect | null, viewport: Size): Rect {
  const width = Math.min(size.width, viewport.width)
  const height = Math.min(size.height, viewport.height)

  const start = origin({ width, height }, viewport)
  const next =
    previous === null
      ? start
      : { x: previous.x + CASCADE_STEP, y: previous.y + CASCADE_STEP }

  const restart =
    next.x + GRAB_MARGIN > viewport.width || next.y + GRAB_MARGIN > viewport.height

  return clamp({ ...(restart ? start : next), width, height }, viewport)
}

/**
 * Give a newly mounted window the size its contents ask for.
 *
 * Content is measured only after Vue has rendered it, so this is separate
 * from `place`. A fit is an opening rule and centres the final rectangle;
 * later ResizeObserver changes grow from the current top-left through
 * `resizeTo`, avoiding a window that jumps around while an error appears.
 */
export function fit(_rect: Rect, content: Size, viewport: Size): Rect {
  const width = Math.min(content.width, viewport.width)
  const height = Math.min(content.height, viewport.height)
  return {
    x: bounded(Math.round(_rect.x + (_rect.width - width) / 2), 0, viewport.width - width),
    y: bounded(Math.round(_rect.y + (_rect.height - height) / 2), 0, viewport.height - height),
    width,
    height,
  }
}

/** Resize to an exact measured size without moving the window. */
export function resizeTo(rect: Rect, size: Size, viewport: Size): Rect {
  const width = bounded(size.width, 1, viewport.width)
  const height = bounded(size.height, 1, viewport.height)
  return {
    x: bounded(rect.x, 0, viewport.width - width),
    y: bounded(rect.y, 0, viewport.height - height),
    width,
    height,
  }
}

/**
 * Resize from any border or corner. Unlike moving, manual sizing stays
 * wholly inside the viewport: a resize handle that leaves the screen cannot
 * be grabbed again.
 */
export function resize(
  rect: Rect,
  edge: ResizeEdge,
  pointer: { x: number; y: number },
  viewport: Size,
  minimum: Size
): Rect {
  const right = rect.x + rect.width
  const bottom = rect.y + rect.height
  let left = rect.x
  let top = rect.y
  let nextRight = right
  let nextBottom = bottom

  if (edge.includes("left")) left = bounded(pointer.x, 0, right - minimum.width)
  if (edge.includes("right")) {
    nextRight = bounded(pointer.x, rect.x + minimum.width, viewport.width)
  }
  if (edge.includes("top")) top = bounded(pointer.y, 0, bottom - minimum.height)
  if (edge.includes("bottom")) {
    nextBottom = bounded(pointer.y, rect.y + minimum.height, viewport.height)
  }

  return { x: left, y: top, width: nextRight - left, height: nextBottom - top }
}

/**
 * The stacking order, front last.
 *
 * A position in a list rather than a z-index counter: the old engine
 * incremented one for ever and had no way back from it. Here focusing a
 * thousand times leaves a list of the same three windows.
 */
export function bringToFront(order: readonly string[], id: string): string[] {
  if (!order.includes(id)) return [...order]
  return [...order.filter((other) => other !== id), id]
}
