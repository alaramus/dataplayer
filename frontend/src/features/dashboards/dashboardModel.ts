/**
 * What can be done to the content of a dashboard, as plain functions over it.
 *
 * The screen holds a draft of the dashboard and saves it whole; every change is
 * one of these, so what a change does can be read and tested without mounting.
 */

import type { DashboardOptions, ProcessesWidget, StatWidget, TimeseriesWidget } from "@/client"

import { compact, findFreeSpot, gridRows } from "./gridLayout"
import type { Placed } from "./gridLayout"
import type { WidgetDraft } from "./widgetSpecs"

export type Widget = TimeseriesWidget | StatWidget | ProcessesWidget
export type ProcessSort = NonNullable<ProcessesWidget["sort"]>
export type ProcessLimit = NonNullable<ProcessesWidget["limit"]>

export const PROCESS_SORTS: { value: ProcessSort; label: string }[] = [
  { value: "pcpu", label: "By CPU" },
  { value: "pmem", label: "By memory" },
  { value: "pid", label: "By PID" },
]
export const PROCESS_LIMITS: { value: ProcessLimit; label: string }[] = [10, 20, 50, 100, 200].map(
  (value) => ({ value: value as ProcessLimit, label: `${String(value)} rows` })
)

/** Mirrors MAX_WIDGETS in app/metrics/dashboards.py. */
export const MAX_WIDGETS = 20
export const MAX_TITLE = 120

/** A tile needs room to be large, not room to be long. */
const SIZE = { timeseries: { w: 6, h: 5 }, stat: { w: 3, h: 5 }, processes: { w: 12, h: 8 } } as const

export type RangeSeconds = NonNullable<DashboardOptions["range_seconds"]>
export type RefreshSeconds = NonNullable<DashboardOptions["refresh_seconds"]>

export const RANGES: { value: RangeSeconds; label: string }[] = [
  { value: 300, label: "Last 5 minutes" },
  { value: 900, label: "Last 15 minutes" },
  { value: 3600, label: "Last hour" },
  { value: 21600, label: "Last 6 hours" },
  { value: 86400, label: "Last 24 hours" },
  { value: 604800, label: "Last 7 days" },
  { value: 2592000, label: "Last 30 days" },
]

export const REFRESHES: { value: RefreshSeconds; label: string }[] = [
  { value: 0, label: "Off" },
  { value: 10, label: "10 s" },
  { value: 30, label: "30 s" },
  { value: 60, label: "1 min" },
  { value: 300, label: "5 min" },
]

export function seriesOfWidget(widget: Widget): number[] {
  if (widget.type === "stat") return [widget.series_id]
  if (widget.type === "timeseries") return widget.series_ids
  return []
}

export function placedOf(widgets: readonly Widget[]): Placed[] {
  return widgets.map((widget) => ({ id: widget.id, layout: widget.layout }))
}

export function withLayout(widgets: readonly Widget[], placed: readonly Placed[]): Widget[] {
  const byId = new Map(placed.map((item) => [item.id, item.layout]))
  return widgets.map((widget) => {
    const layout = byId.get(widget.id)
    return layout === undefined ? widget : { ...widget, layout }
  })
}

/**
 * Drafts placed after what is there. Returns how many did not fit under the
 * ceiling, because a set that half fits is still worth adding and the silence
 * is what would need explaining.
 */
export function withDrafts(
  widgets: readonly Widget[],
  drafts: readonly WidgetDraft[],
  newId: () => string
): { widgets: Widget[]; left: number } {
  const result = [...widgets]
  let left = 0
  for (const draft of drafts) {
    if (result.length >= MAX_WIDGETS) {
      left += 1
      continue
    }
    const size = SIZE[draft.type]
    const spot = findFreeSpot(placedOf(result), size.w, size.h)
    const layout = { ...spot, ...size }
    const title = draft.title.slice(0, MAX_TITLE)
    if (draft.type === "stat") {
      result.push({ type: "stat", id: newId(), title, layout, series_id: draft.seriesId })
    } else if (draft.type === "timeseries") {
      result.push({ type: "timeseries", id: newId(), title, layout, series_ids: draft.seriesIds })
    } else {
      result.push({ type: "processes", id: newId(), title, layout, agent_id: draft.agentId, host: draft.host })
    }
  }
  return { widgets: result, left }
}

/**
 * A ready-made layout placed under what is there, its widgets keeping their
 * places relative to each other; the grid then settles the lot, which also
 * closes the gaps of recipes the host could not fill.
 */
export function withPreset(
  widgets: readonly Widget[],
  preset: readonly Widget[],
  newId: () => string
): { widgets: Widget[]; left: number } {
  const room = Math.max(0, MAX_WIDGETS - widgets.length)
  const below = gridRows(placedOf(widgets))
  const taken = preset.slice(0, room).map((widget) => ({
    ...widget,
    id: newId(),
    layout: { ...widget.layout, y: widget.layout.y + below },
  }))
  const all = [...widgets, ...taken]
  return { widgets: withLayout(all, compact(placedOf(all))), left: preset.length - taken.length }
}

export function withOptions(
  widgets: readonly Widget[],
  id: string,
  patch: { sort?: ProcessSort; limit?: ProcessLimit }
): Widget[] {
  return widgets.map((widget) => (widget.id === id && widget.type === "processes" ? { ...widget, ...patch } : widget))
}

export function withoutWidget(widgets: readonly Widget[], id: string): Widget[] {
  const remaining = widgets.filter((widget) => widget.id !== id)
  return withLayout(remaining, compact(placedOf(remaining)))
}

export function renamed(widgets: readonly Widget[], id: string, title: string): Widget[] {
  const clean = title.trim().slice(0, MAX_TITLE)
  return widgets.map((widget) => (widget.id === id ? { ...widget, title: clean } : widget))
}

/** The range a history request asks for, ending now. */
export function windowOf(rangeSeconds: number, nowMs: number): { start: number; end: number } {
  const end = Math.floor(nowMs / 1000)
  return { start: end - rangeSeconds, end }
}
