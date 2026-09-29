/**
 * How a dashboard is marked in the rail, wide or narrow.
 *
 * A dashboard with a colour is drawn the way a connection with one is: washed
 * in it while it is not open, filled with it while it is. One without is
 * marked the way the current page of any list is, on the tab ground (D186):
 * filling it with the plain panel colour is the card itself in the dark
 * theme, and the blue text it had was a colour no other list used.
 */

export interface RailEntry {
  variant: "quiet"
  /** Open and without a colour: on the ground of the current tab. */
  current: boolean
  /** A quiet wash of the dashboard's colour. */
  tinted: boolean
  /** Filled with it, and written in the colour readable on it. */
  filled: boolean
}

export function railEntry(color: string | null | undefined, open: boolean): RailEntry {
  const coloured = typeof color === "string" && /^#[\da-f]{6}$/i.test(color)
  if (!coloured) return { variant: "quiet", current: open, tinted: false, filled: false }
  return { variant: "quiet", current: false, tinted: !open, filled: open }
}
