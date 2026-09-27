import { COLLAPSED_PX } from "./model"

/** Shared two-card rail sizing: narrow enough to leave the main card primary. */
export const RAIL_NARROW_PX = COLLAPSED_PX
export const RAIL_DEFAULT_PX = 260
/** Also the narrowest the column of connections is dragged to (WorkspacePage). */
export const RAIL_MIN_PX = 200
export const RAIL_MAX_SHARE = 0.4

export function clampRailWidth(width: number, spaceWidth: number): number {
  const ceiling = Math.max(RAIL_MIN_PX, Math.floor(spaceWidth * RAIL_MAX_SHARE))
  return Math.round(Math.min(Math.max(width, RAIL_MIN_PX), ceiling))
}

export function parseRailNarrow(stored: string | null): boolean {
  return stored === "narrow"
}

export function parseRailWidth(stored: string | null): number {
  const width = Number(stored)
  return stored !== null && Number.isFinite(width) && width > 0 ? width : RAIL_DEFAULT_PX
}
