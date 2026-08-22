import type { DropZone } from "./model"

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

/** How much of a side counts as its edge. */
const EDGE = 0.25

/**
 * Where a dragged panel would land if it were released here.
 *
 * The wider side wins in a corner: with the pointer in the top-left of a wide
 * section, splitting sideways is what the user is more likely to mean, and a
 * rule is better than whichever comparison happens to run first.
 */
export function dropZoneAt(rect: Rect, x: number, y: number): DropZone {
  if (rect.width <= 0 || rect.height <= 0) return "center"

  const fx = (x - rect.left) / rect.width
  const fy = (y - rect.top) / rect.height

  const horizontal: DropZone | null = fx < EDGE ? "left" : fx > 1 - EDGE ? "right" : null
  const vertical: DropZone | null = fy < EDGE ? "top" : fy > 1 - EDGE ? "bottom" : null

  if (horizontal !== null && vertical !== null) {
    return rect.width >= rect.height ? horizontal : vertical
  }
  return horizontal ?? vertical ?? "center"
}
