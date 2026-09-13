/**
 * What can be done to the content of a dashboard, as plain functions over it.
 *
 * The screen holds a draft of the dashboard and saves it whole; every change is
 * one of these, so what a change does can be read and tested without mounting.
 */

import type { DashboardOptions, StatWidget, TimeseriesWidget } from "@/client"

import { compact, findFreeSpot } from "./gridLayout"
import type { Placed } from "./gridLayout"
import type { WidgetDraft } from "./widgetSpecs"

export type Widget = TimeseriesWidget | StatWidget

/** Mirrors MAX_WIDGETS in app/metrics/dashboards.py. */
export const MAX_WIDGETS = 20
export const MAX_TITLE = 120

/** A tile needs room to be large, not room to be long. */
const SIZE = { timeseries: { w: 6, h: 5 }, stat: { w: 3, h: 5 } } as const

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
  return widget.type === "stat" ? [widget.series_id] : widget.series_ids
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
    result.push(
      draft.type === "stat"
        ? { type: "stat", id: newId(), title, layout, series_id: draft.seriesId }
        : { type: "timeseries", id: newId(), title, layout, series_ids: draft.seriesIds }
    )
  }
  return { widgets: result, left }
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
