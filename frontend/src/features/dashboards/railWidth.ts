/**
 * How wide the dashboards rail is (D125).
 *
 * Dragged by the gap beside it, the way two workspace columns are, and held
 * narrower than the dashboard: never more than two fifths of the space, never
 * too narrow for its own buttons. The floor wins on a window so narrow that
 * both cannot hold.
 */

export const RAIL_DEFAULT_PX = 260
export const RAIL_MIN_PX = 200
export const RAIL_MAX_SHARE = 0.4

export function clampRailWidth(width: number, spaceWidth: number): number {
  const ceiling = Math.max(RAIL_MIN_PX, Math.floor(spaceWidth * RAIL_MAX_SHARE))
  return Math.round(Math.min(Math.max(width, RAIL_MIN_PX), ceiling))
}

/** A stored width, or the default for anything that is not one. */
export function parseRailWidth(stored: string | null): number {
  const width = Number(stored)
  return stored !== null && Number.isFinite(width) && width > 0 ? width : RAIL_DEFAULT_PX
}
