/** Where the hint of a tour stands beside the control it is about (D355). */

export interface Box {
  top: number
  left: number
  width: number
  height: number
}

export interface Size {
  width: number
  height: number
}

/** Kept clear of the window's edges and of the ring around the control. */
export const EDGE = 16
export const GAP = 12

function fits(spot: { top: number; left: number }, card: Size, viewport: Size): boolean {
  return (
    spot.left >= EDGE &&
    spot.top >= EDGE &&
    spot.left + card.width <= viewport.width - EDGE &&
    spot.top + card.height <= viewport.height - EDGE
  )
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), Math.max(low, high))
}

/**
 * Beside the control rather than over it: to the right, then the left, then
 * below, then above — the side where it fits first. A control too large for
 * any side (a whole editor) gets the hint in its lower right corner. With no
 * control on screen the hint waits in the lower right of the window.
 */
export function placeHint(target: Box | null, card: Size, viewport: Size): { top: number; left: number } {
  const corner = {
    top: viewport.height - EDGE - card.height,
    left: viewport.width - EDGE - card.width,
  }
  if (target === null) return corner

  const middleTop = clamp(target.top + target.height / 2 - card.height / 2, EDGE, corner.top)
  const middleLeft = clamp(target.left + target.width / 2 - card.width / 2, EDGE, corner.left)
  const spots = [
    { top: middleTop, left: target.left + target.width + GAP },
    { top: middleTop, left: target.left - GAP - card.width },
    { top: target.top + target.height + GAP, left: middleLeft },
    { top: target.top - GAP - card.height, left: middleLeft },
  ]
  const spot = spots.find((candidate) => fits(candidate, card, viewport))
  if (spot !== undefined) return spot
  return {
    top: clamp(target.top + target.height - card.height - GAP, EDGE, corner.top),
    left: clamp(target.left + target.width - card.width - GAP, EDGE, corner.left),
  }
}
