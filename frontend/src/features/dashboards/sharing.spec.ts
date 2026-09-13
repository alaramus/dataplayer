import { describe, expect, it } from "vitest"

import type { SeriesEntry } from "./catalog"
import { dashboardLinkFor, levelLabel, mayEdit, mayManage, mergedIndex, splitByOwner } from "./sharing"

describe("what a person may do with a dashboard", () => {
  it("lets a reader look, an editor change it, and only its owner share or delete it", () => {
    expect([mayEdit({ access: "read" }), mayManage({ access: "read" })]).toEqual([false, false])
    expect([mayEdit({ access: "write" }), mayManage({ access: "write" })]).toEqual([true, false])
    expect([mayEdit({ access: "own" }), mayManage({ access: "own" })]).toEqual([true, true])
  })

  it("names the levels the way the share window offers them", () => {
    expect(levelLabel("read")).toBe("Can view")
    expect(levelLabel("write")).toBe("Can edit")
  })

  it("lists one's own dashboards apart from those shared with one", () => {
    const listed = [{ id: "a", access: "own" as const }, { id: "b", access: "read" as const }, { id: "c", access: "write" as const }]

    const { own, shared } = splitByOwner(listed)

    expect(own.map((one) => one.id)).toEqual(["a"])
    expect(shared.map((one) => one.id)).toEqual(["b", "c"])
  })
})

describe("the address of a dashboard", () => {
  it("names the dashboard and, when there are several, the server", () => {
    expect(dashboardLinkFor("d-1", "http://localhost:5173")).toBe("http://localhost:5173/dashboards/d-1")
    expect(dashboardLinkFor("d-1", "http://localhost:5173", "http://api:8000")).toBe(
      "http://localhost:5173/dashboards/d-1?server=http%3A%2F%2Fapi%3A8000"
    )
  })
})

describe("names of the series on a shared dashboard", () => {
  it("adds what is read through the dashboard to what is read directly", () => {
    const entry = (host: string) => ({ host }) as SeriesEntry
    const direct = new Map([[1, entry("mine")]])
    const through = new Map([[1, entry("stale")], [2, entry("theirs")]])

    const merged = mergedIndex(direct, through)

    expect(merged.get(1)?.host).toBe("mine")
    expect(merged.get(2)?.host).toBe("theirs")
  })
})
