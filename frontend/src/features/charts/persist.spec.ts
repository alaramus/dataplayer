import { beforeEach, describe, expect, it } from "vitest"

import { chartStorageKey, loadChartSpec, moveChartSpec, saveChartSpec } from "./persist"

beforeEach(() => localStorage.clear())

describe("a remembered chart choice", () => {
  it("round-trips only a closed chart specification", () => {
    saveChartSpec("view", { type: "bar", x: "team", y: "amount" })
    expect(loadChartSpec("view")).toEqual({ type: "bar", x: "team", y: "amount" })
  })

  it("refuses arbitrary renderer configuration", () => {
    localStorage.setItem(
      chartStorageKey("view"),
      JSON.stringify({ type: "bar", x: "team", y: "amount", series: [{ eval: "x" }] })
    )
    expect(loadChartSpec("view")).toBeNull()
  })

  it("moves the choice when a source replaces its node identity", () => {
    saveChartSpec("old", { type: "line", x: "$row", y: "amount" })
    moveChartSpec("old", "new")
    expect(loadChartSpec("old")).toBeNull()
    expect(loadChartSpec("new")).toEqual({ type: "line", x: "$row", y: "amount" })
  })
})
