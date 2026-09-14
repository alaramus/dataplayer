import { describe, expect, it } from "vitest"

import { MAX_WIDGETS, renamed, windowOf, withDrafts, withoutWidget } from "./dashboardModel"
import type { Widget } from "./dashboardModel"

function ids(): () => string {
  let next = 0
  return () => {
    next += 1
    return `w${String(next)}`
  }
}

describe("the content of a dashboard", () => {
  it("places new widgets after what is there, a tile narrower than a chart", () => {
    const { widgets, left } = withDrafts(
      [],
      [
        { type: "timeseries", title: "cpu · h", seriesIds: [1, 2] },
        { type: "stat", title: "h · uptime", seriesId: 3 },
        { type: "timeseries", title: "memory · h", seriesIds: [4] },
      ],
      ids()
    )

    expect(left).toBe(0)
    expect(widgets.map((widget) => widget.layout)).toEqual([
      { x: 0, y: 0, w: 6, h: 5 },
      { x: 6, y: 0, w: 3, h: 5 },
      { x: 0, y: 5, w: 6, h: 5 },
    ])
    expect(widgets[1]).toMatchObject({ type: "stat", series_id: 3 })
  })

  it("stops at the ceiling and says how many did not fit", () => {
    const drafts = Array.from({ length: MAX_WIDGETS + 2 }, (_, i) => ({
      type: "stat" as const,
      title: `t${String(i)}`,
      seriesId: i,
    }))

    const { widgets, left } = withDrafts([], drafts, ids())

    expect(widgets).toHaveLength(MAX_WIDGETS)
    expect(left).toBe(2)
  })

  it("closes a gap left by a removed widget", () => {
    const { widgets } = withDrafts(
      [],
      [
        { type: "timeseries", title: "a", seriesIds: [1] },
        { type: "timeseries", title: "b", seriesIds: [2] },
        { type: "timeseries", title: "c", seriesIds: [3] },
      ],
      ids()
    )

    const remaining: Widget[] = withoutWidget(widgets, "w1")

    expect(remaining.map((widget) => [widget.id, widget.layout.y])).toEqual([
      ["w2", 0],
      ["w3", 0],
    ])
  })

  it("trims a title to what the server accepts", () => {
    const { widgets } = withDrafts([], [{ type: "stat", title: "x", seriesId: 1 }], ids())

    expect(renamed(widgets, "w1", `  ${"a".repeat(200)}  `)[0]?.title).toHaveLength(120)
  })

  it("asks for the range ending now", () => {
    expect(windowOf(900, 1_789_000_000_500)).toEqual({ start: 1_788_999_100, end: 1_789_000_000 })
  })
})
