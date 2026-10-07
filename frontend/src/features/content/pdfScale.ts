/** How wide a page is drawn, given the room there is for it. */
const MIN_SCALE = 0.25
const MAX_SCALE = 3
/**
 * Room for the scrollbar the pages bring.
 *
 * Measured before the pages exist, so the vertical scrollbar is not in the
 * width yet; without this the first page is a scrollbar too wide and the panel
 * scrolls sideways. The stage keeps no side padding and the scrollbars are
 * thin (`--dp-scrollbar-size`), so a dozen pixels cover it.
 */
const MARGIN = 12

/**
 * Fit the page to the width available, within honest bounds.
 *
 * A pure function because the arithmetic is the part worth testing: a panel
 * that has not been laid out yet reports no width, and a page scaled to zero
 * renders nothing at all with no error to show for it.
 */
export function pageScale(available: number, pageWidth: number): number {
  if (pageWidth <= 0) return 1
  if (available <= MARGIN) return 1
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, (available - MARGIN) / pageWidth))
}
