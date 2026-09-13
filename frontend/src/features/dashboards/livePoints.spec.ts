import { describe, expect, it } from "vitest"

import type { HistoryAnswer, MetricsCatalog, TimeseriesWidget } from "@/client"

import { catalogTree, connectorOfKey, hostOfKey, indexCatalog, processesKey, tickedProcesses } from "./catalog"
import { MAX_WIDGETS, withOptions, withPreset } from "./dashboardModel"
import type { Widget } from "./dashboardModel"
import { isLivePoints, mergeLive } from "./livePoints"
import { draftsFor } from "./widgetSpecs"

const AGENT = "0b5b7a1e-2f6a-4c44-9f3e-7d2f4c8a9b10"

function raw(points: number[][]): HistoryAnswer {
  return { start: 1000, end: 1900, bucket_seconds: null, series: [{ series_id: 1, points }] }
}

describe("points from the socket on a history already read", () => {
  it("appends what is newer and drops what fell out of the range", () => {
    const merged = mergeLive(raw([[1000, 1], [1030, 2]]), { series: [{ series_id: 1, points: [[1060, 3]] }] }, 50, 1060)

    expect(merged?.series[0]?.points).toEqual([[1030, 2], [1060, 3]])
  })

  it("changes nothing twice, and nothing it does not hold", () => {
    const once = mergeLive(raw([[1000, 1]]), { series: [{ series_id: 1, points: [[1030, 2]] }] }, 900, 1030)
    expect(once).not.toBeNull()
    if (once === null) return

    expect(mergeLive(once, { series: [{ series_id: 1, points: [[1030, 2]] }] }, 900, 1030)).toBeNull()
    expect(mergeLive(once, { series: [{ series_id: 9, points: [[1060, 2]] }] }, 900, 1060)).toBeNull()
  })

  it("leaves a bucketed answer to be read again", () => {
    const bucketed = { ...raw([[1000, 1, 0, 2]]), bucket_seconds: 60 }

    expect(mergeLive(bucketed, { series: [{ series_id: 1, points: [[1060, 3]] }] }, 900, 1060)).toBeNull()
  })

  it("recognises what the topic sends", () => {
    expect(isLivePoints({ series: [{ series_id: 1, points: [[1, 2]] }] })).toBe(true)
    expect(isLivePoints({ series: [{ series_id: "1" }] })).toBe(false)
    expect(isLivePoints(null)).toBe(false)
  })
})

describe("process tables in the catalog", () => {
  const catalog: MetricsCatalog = {
    agents: [
      {
        agent_id: AGENT,
        name: "agent",
        hosts: [{ host: "web:01", last_seen: "", metrics: [], processes: true }],
      },
    ],
  }

  it("draws a leaf for a host that sends them, and reads it back even with a colon in the host", () => {
    const leaf = catalogTree(catalog)[0]?.children?.[0]?.children?.[0]

    expect(leaf?.key).toBe(processesKey({ agentId: AGENT, host: "web:01" }))
    expect(tickedProcesses([String(leaf?.key), "series:4"])).toEqual([{ agentId: AGENT, host: "web:01" }])
    expect(hostOfKey(`host:${AGENT}:web:01`)).toEqual({ agentId: AGENT, host: "web:01" })
    expect(hostOfKey("metric:x")).toBeNull()
  })

  it("becomes a table widget of its own", () => {
    expect(draftsFor([], [{ agentId: AGENT, host: "db" }])).toEqual([
      { type: "processes", title: "Processes · db", agentId: AGENT, host: "db" },
    ])
  })
})

describe("a ready-made layout on a dashboard", () => {
  function chart(id: string, x: number, y: number): TimeseriesWidget {
    return { type: "timeseries", id, title: id, layout: { x, y, w: 6, h: 5 }, series_ids: [1] }
  }
  let next = 0
  const newId = () => {
    next += 1
    return `new${String(next)}`
  }

  it("goes under what is there, keeps its own arrangement, and closes its gaps", () => {
    const existing: Widget[] = [chart("a", 0, 0)]
    // The preset's second row is missing: its host did not fill that recipe.
    const preset: Widget[] = [chart("p1", 0, 0), chart("p2", 6, 0), chart("p3", 0, 10)]

    const { widgets, left } = withPreset(existing, preset, newId)

    expect(left).toBe(0)
    expect(widgets.map((widget) => [widget.layout.x, widget.layout.y])).toEqual([[0, 0], [0, 5], [6, 0], [0, 10]])
    expect(new Set(widgets.map((widget) => widget.id)).size).toBe(4)
    expect(widgets.some((widget) => widget.id === "p1")).toBe(false)
  })

  it("stops at the ceiling and says how many were left", () => {
    const existing = Array.from({ length: MAX_WIDGETS - 1 }, (_, i) => chart(`e${String(i)}`, 0, i * 5))

    expect(withPreset(existing, [chart("p1", 0, 0), chart("p2", 6, 0)], newId).left).toBe(1)
  })

  it("changes a table's sort and rows and nothing else", () => {
    const table: Widget = {
      type: "processes", id: "t", title: "t", layout: { x: 0, y: 0, w: 12, h: 8 }, agent_id: AGENT, host: "db",
    }

    expect(withOptions([table, chart("c", 0, 8)], "t", { sort: "pmem" })[0]).toMatchObject({ sort: "pmem", host: "db" })
    expect(withOptions([chart("c", 0, 0)], "c", { limit: 50 })[0]).not.toHaveProperty("limit")
  })
})

describe("connections in the catalog", () => {
  const catalog: MetricsCatalog = {
    agents: [],
    connectors: [
      {
        connector_id: "c1",
        name: "orders db",
        adapter_type: "postgres",
        last_seen: "",
        metrics: [
          { metric: "sessions", series: [{ id: 7, field: "count", label: "active", unit: "", first_seen: "", last_seen: "" }] },
        ],
      },
    ],
  }

  it("is a branch of its own, named and drawn by its type, and read back", () => {
    const [node] = catalogTree(catalog)

    expect(node?.label).toBe("orders db")
    expect(node?.icon).toBe("img:/icons/services/postgresql.svg")
    expect(connectorOfKey(String(node?.key))).toBe("c1")
    expect(connectorOfKey("host:x")).toBeNull()
  })

  it("names its series after the connection", () => {
    const entry = indexCatalog(catalog).get(7)

    expect(entry).toMatchObject({ sourceId: "c1", host: "orders db", metric: "sessions" })
    expect(draftsFor(entry === undefined ? [] : [entry])[0]?.title).toBe("sessions · orders db")
  })
})

