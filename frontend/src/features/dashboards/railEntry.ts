/**
 * How a dashboard is marked in the rail, wide or narrow.
 *
 * A dashboard with a colour is drawn the way a connection with one is: washed
 * in it while it is not open, filled with it while it is. One without stays as
 * it was — the open one written in blue — because filling it with the plain
 * panel colour is the card itself in the dark theme.
 */

export interface RailEntry {
  variant: "secondary" | "quiet"
  /** A quiet wash of the dashboard's colour. */
  tinted: boolean
  /** Filled with it, and written in the colour readable on it. */
  filled: boolean
}

export function railEntry(color: string | null | undefined, open: boolean): RailEntry {
  const coloured = typeof color === "string" && /^#[\da-f]{6}$/i.test(color)
  if (!coloured) return { variant: open ? "secondary" : "quiet", tinted: false, filled: false }
  return { variant: "quiet", tinted: !open, filled: open }
}
