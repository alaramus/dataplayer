import type { DropZone } from "./model"

export interface Rect {
  left: number
  top: number
  width: number
  height: number
}

/**
 * A section, as a drop target: two rectangles that mean different things.
 *
 * The strip of tabs is where a panel joins the ones already there; the body is
 * where it divides the section. One target per intention — see the spec, G3.
 */
export interface SectionRects {
  strip: Rect
  body: Rect
}

function contains(rect: Rect, x: number, y: number): boolean {
  return (
    rect.width > 0 &&
    rect.height > 0 &&
    x >= rect.left &&
    x <= rect.left + rect.width &&
    y >= rect.top &&
    y <= rect.top + rect.height
  )
}

/**
 * Where a dragged panel would land if it were released here.
 *
 * In the body the nearest edge wins, with nothing neutral in between: "beside
 * the others" is what the strip means, and a body meaning it too would be a
 * second way to one result. Nearness is a share of the side and not a distance
 * in pixels — in pixels the top and bottom of a wide section would claim
 * almost all of it. A tie goes to the wider side (G4).
 */
export function dropZoneAt(rects: SectionRects, x: number, y: number): DropZone {
  if (contains(rects.strip, x, y)) return "center"

  const { body } = rects
  if (body.width <= 0 || body.height <= 0) return "center"

  const fx = (x - body.left) / body.width
  const fy = (y - body.top) / body.height

  const horizontal: { zone: DropZone; distance: number } =
    fx <= 0.5 ? { zone: "left", distance: fx } : { zone: "right", distance: 1 - fx }
  const vertical: { zone: DropZone; distance: number } =
    fy <= 0.5 ? { zone: "top", distance: fy } : { zone: "bottom", distance: 1 - fy }

  if (horizontal.distance === vertical.distance) {
    return body.width >= body.height ? horizontal.zone : vertical.zone
  }
  return horizontal.distance < vertical.distance ? horizontal.zone : vertical.zone
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
  rects: SectionRects,
  x: number,
  y: number,
  admission: DropAdmission
): DropZone | null {
  return admittedZone(dropZoneAt(rects, x, y), admission)
}

/**
 * Which place in a strip of tabs the pointer is between: the index the dragged
 * panel takes if released now, 0 before the first and `tabs.length` after the
 * last. A tab is claimed by whichever half the pointer is in, so the mark
 * moves at its middle rather than its edge.
 *
 * The rectangles are the tabs that are drawn, and the one in the hand is not
 * among them, so this is already an index into the strip as it will be.
 */
export function insertionAt(tabs: readonly Rect[], x: number): number {
  for (const [index, tab] of tabs.entries()) {
    if (x < tab.left + tab.width / 2) return index
  }
  return tabs.length
}

/** What is lit up while a panel is held over a section. */
export type DropShape = "none" | "strip" | "half" | "whole"

/**
 * The highlight shows where the panel will end up, not which zone the pointer
 * happens to be in.
 *
 * A tab joining the others ends up in the head, so the head lights up; a whole
 * panel lit for that describes a result that will not happen. The one case
 * where the whole section is honest is the section that holds nothing: the
 * panel really will fill it. See G5.
 */
export function dropShape(zone: DropZone | null, empty: boolean): DropShape {
  if (zone === null) return "none"
  if (zone !== "center") return "half"
  return empty ? "whole" : "strip"
}
