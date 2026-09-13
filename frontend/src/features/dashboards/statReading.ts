/**
 * What a tile says about one series: its last value, and for a counter that
 * climbs from a moment — uptime — when that moment was and whether the count
 * fell inside the range, which for such a counter is a restart.
 */

export interface StatReading {
  value: number
  at: number
  /** Seconds since the epoch the count started from, for a series in seconds. */
  since: number | null
  restarted: boolean
}

export function readStat(points: readonly (readonly number[])[], unit: string): StatReading | null {
  const last = points.at(-1)
  if (last === undefined) return null
  const [at, value] = last
  if (at === undefined || value === undefined) return null
  let restarted = false
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1]?.[1]
    const current = points[index]?.[1]
    if (previous !== undefined && current !== undefined && current < previous) restarted = true
  }
  return {
    value,
    at,
    // The sample's own moment minus its value, never the browser's clock.
    since: unit === "s" ? at - value : null,
    restarted: unit === "s" && restarted,
  }
}
