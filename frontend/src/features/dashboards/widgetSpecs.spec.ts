import { describe, expect, it } from "vitest"

import type { MetricsCatalog } from "@/client"

import { catalogTree, indexCatalog, seriesKey, seriesName, tickedSeries } from "./catalog"
import type { SeriesEntry } from "./catalog"
import { draftsFor, MAX_SERIES_PER_WIDGET } from "./widgetSpecs"

let nextId = 1

function entry(host: string, metric: string, field: string, label: string, unit: string): SeriesEntry {
  nextId += 1
  return { id: nextId, sourceId: "a", sourceName: "agent", host, metric, field, label, unit, lastSeen: "" }
}

const CATALOG: MetricsCatalog = {
  agents: [
    {
      agent_id: "a1",
      name: "Development agent",
      hosts: [
        {
          host: "dev-agent",
          last_seen: "2026-09-13T07:26:56Z",
          metrics: [
            {
              metric: "host",
              series: [
                { id: 1, field: "processes", label: "", unit: "", first_seen: "", last_seen: "" },
                { id: 2, field: "uptime", label: "", unit: "s", first_seen: "", last_seen: "" },
              ],
            },
          ],
        },
      ],
    },
  ],
}

describe("the catalog of what agents reported", () => {
  it("indexes every series with where it came from", () => {
    const index = indexCatalog(CATALOG)

    expect(index.get(1)).toMatchObject({ host: "dev-agent", metric: "host", field: "processes", label: "", unit: "" })
    expect(index.size).toBe(2)
    expect(indexCatalog(undefined).size).toBe(0)
  })

  it("names a series with its host only where hosts must be told apart", () => {
    const index = indexCatalog(CATALOG)

    expect(seriesName(index.get(1)!, false)).toBe("processes")
    expect(seriesName(index.get(2)!, true)).toBe("dev-agent · uptime")
  })

  it("draws agents, hosts, metrics and series, and reads ticks back", () => {
    const tree = catalogTree(CATALOG)

    expect(tree[0]?.label).toBe("Development agent")
    const series = tree[0]?.children?.[0]?.children?.[0]?.children ?? []
    expect(series.map((node) => node.key)).toEqual([seriesKey(1), seriesKey(2)])
    expect(tickedSeries(["agent:a1", seriesKey(2), "metric:x"])).toEqual([2])
  })
})

describe("ticked series turned into widgets", () => {
  it("makes uptime a tile and the rest a chart per metric", () => {
    const uptime = entry("web-01", "host", "uptime", "", "s")
    const total = entry("web-01", "cpu", "utilization", "total", "%")
    const core = entry("web-01", "cpu", "utilization", "cpu0", "%")

    expect(draftsFor([uptime, total, core])).toEqual([
      { type: "stat", title: "web-01 · uptime", seriesId: uptime.id },
      { type: "timeseries", title: "cpu · web-01", seriesIds: [total.id, core.id] },
    ])
  })

  it("keeps one metric of several hosts on one chart", () => {
    const a = entry("web-01", "memory", "available", "", "B")
    const b = entry("db-01", "memory", "available", "", "B")

    expect(draftsFor([a, b])).toEqual([
      { type: "timeseries", title: "memory · 2 hosts", seriesIds: [a.id, b.id] },
    ])
  })

  it("splits a metric by unit and says so, and never mixes metrics that share one", () => {
    const load = entry("h", "cpu", "load1", "", "")
    const busy = entry("h", "cpu", "utilization", "total", "%")
    const memory = entry("h", "memory", "available", "", "B")
    const used = entry("h", "fs", "used", "/", "B")

    const titles = draftsFor([load, busy, memory, used]).map((draft) => draft.title)

    expect(titles).toEqual(["cpu · h", "cpu (%) · h", "memory · h", "fs · h"])
  })

  it("never puts more series on a chart than the server accepts", () => {
    const many = Array.from({ length: MAX_SERIES_PER_WIDGET + 3 }, (_, i) =>
      entry("h", "container", "cpu", `container${String(i)}`, "%")
    )

    const drafts = draftsFor(many)

    expect(drafts).toHaveLength(2)
    expect(drafts.map((draft) => (draft.type === "timeseries" ? draft.seriesIds.length : 1))).toEqual([
      MAX_SERIES_PER_WIDGET,
      3,
    ])
  })
})
