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

/**
 * What a section will take from the drag now in progress.
 *
 * Two facts and no notion of what a panel is: the engine compares two opaque
 * role strings and counts panels, exactly as `leafForKind` does. See P1.
 */
export interface DropAdmission {
  /** Whether the role of the dragged panel is the role this section takes. */
  accepts: boolean
  /** How many panels the section would hold once the dragged one has left it. */
  remaining: number
}

/**
 * The zone a section will honour, or null for one that refuses.
 *
 * Null rather than a silent fallback: a zone that is not offered is not
 * highlighted either, and refusing after the button is released is worse than
 * never promising. See P1.
 */
export function admittedZone(zone: DropZone, admission: DropAdmission): DropZone | null {
  if (!admission.accepts) return null
  // A side that would leave the target with nothing is not a split - it is
  // the same panel in the same place beside an empty half. What the gesture
  // can still mean is "put it here". See P3.
  if (zone !== "center" && admission.remaining === 0) return "center"
  return zone
}

/** Where a dragged panel would land here, once the section has had its say. */
export function dropZoneFor(
  rect: Rect,
  x: number,
  y: number,
  admission: DropAdmission
): DropZone | null {
  return admittedZone(dropZoneAt(rect, x, y), admission)
}
