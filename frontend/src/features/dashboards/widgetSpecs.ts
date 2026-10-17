/**
 * Ticked series turned into the widgets that draw them. There is no widget
 * type to choose.
 *
 * - A series that is a state rather than a trend becomes a tile: uptime counts
 *   up one second per second, so its line says nothing and its last value
 *   says everything.
 * - Everything else is one chart per (metric, unit): an axis has one scale, and
 *   a unit is not a subject — `memory` and `fs` are both bytes.
 * - Not per host: one metric of several hosts on one chart is the comparison
 *   ticking several is for.
 */

import { t } from "@/shared/i18n"

import { seriesName } from "./catalog"
import type { HostRef, SeriesEntry } from "./catalog"

export const MAX_SERIES_PER_WIDGET = 50

const STATE_SERIES = new Set(["host/uptime"])

export type WidgetDraft =
  | { type: "timeseries"; title: string; seriesIds: number[] }
  | { type: "stat"; title: string; seriesId: number }
  | { type: "processes"; title: string; agentId: string; host: string }

export function isStateSeries(entry: SeriesEntry): boolean {
  return STATE_SERIES.has(`${entry.metric}/${entry.field}`)
}

export function draftsFor(entries: readonly SeriesEntry[], processes: readonly HostRef[] = []): WidgetDraft[] {
  const drafts: WidgetDraft[] = []
  const groups = new Map<string, SeriesEntry[]>()
  for (const entry of entries) {
    if (isStateSeries(entry)) {
      drafts.push({ type: "stat", title: seriesName(entry, true), seriesId: entry.id })
      continue
    }
    const key = `${entry.metric}\u0000${entry.unit}`
    groups.set(key, [...(groups.get(key) ?? []), entry])
  }
  const unitsPerMetric = new Map<string, Set<string>>()
  for (const group of groups.values()) {
    const first = group[0]
    if (first === undefined) continue
    const units = unitsPerMetric.get(first.metric) ?? new Set<string>()
    units.add(first.unit)
    unitsPerMetric.set(first.metric, units)
  }
  for (const group of groups.values()) {
    const first = group[0]
    if (first === undefined) continue
    const hosts = new Set(group.map((entry) => entry.host))
    const where = hosts.size === 1 ? first.host : t("dashboards.drafts.hosts", { n: hosts.size }, hosts.size)
    const split = (unitsPerMetric.get(first.metric)?.size ?? 0) > 1 && first.unit !== ""
    const title = `${first.metric}${split ? ` (${first.unit})` : ""} · ${where}`
    for (let start = 0; start < group.length; start += MAX_SERIES_PER_WIDGET) {
      drafts.push({
        type: "timeseries",
        title,
        seriesIds: group.slice(start, start + MAX_SERIES_PER_WIDGET).map((entry) => entry.id),
      })
    }
  }
  for (const ref of processes) {
    drafts.push({ type: "processes", title: t("dashboards.drafts.processes", { host: ref.host }), agentId: ref.agentId, host: ref.host })
  }
  return drafts
}
