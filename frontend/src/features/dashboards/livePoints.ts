/**
 * New points from the socket laid onto a history already read (D127).
 *
 * Only a raw answer takes them: a bucketed one is an average over a width,
 * and a single sample appended to it would be a point of another kind. Those
 * are read again on the dashboard's interval instead.
 *
 * Idempotent: a point not newer than the last one held is ignored, so the same
 * event delivered to two listeners changes nothing twice.
 */

import type { HistoryAnswer } from "@/client"

export const LIVE_TOPIC = "metrics.points"

export interface LivePoints {
  series: { series_id: number; points: number[][] }[]
}

export function isLivePoints(payload: unknown): payload is LivePoints {
  if (typeof payload !== "object" || payload === null || !("series" in payload)) return false
  const { series } = payload
  return (
    Array.isArray(series) &&
    series.every(
      (one: unknown) =>
        typeof one === "object" &&
        one !== null &&
        "series_id" in one &&
        typeof one.series_id === "number" &&
        "points" in one &&
        Array.isArray(one.points)
    )
  )
}

export function mergeLive(
  answer: HistoryAnswer,
  live: LivePoints,
  rangeSeconds: number,
  nowSeconds: number
): HistoryAnswer | null {
  if (answer.bucket_seconds !== null) return null
  const fresh = new Map(live.series.map((one) => [one.series_id, one.points]))
  const start = nowSeconds - rangeSeconds
  let changed = false
  const series = answer.series.map((one) => {
    const incoming = fresh.get(one.series_id)
    if (incoming === undefined) return one
    const last = one.points.at(-1)?.[0] ?? Number.NEGATIVE_INFINITY
    const newer = incoming.filter((point) => (point[0] ?? 0) > last)
    if (newer.length === 0) return one
    changed = true
    return { ...one, points: [...one.points, ...newer].filter((point) => (point[0] ?? 0) >= start) }
  })
  return changed ? { ...answer, series, end: Math.max(answer.end, nowSeconds) } : null
}
