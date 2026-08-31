import { describe, expect, it } from "vitest"

import { DOCUMENT_SERIES, normalizeLayout, unsupportedSeries } from "./charts"

describe("what a document's chart may ask for", () => {
  it("accepts every series this bundle registers", () => {
    for (const type of DOCUMENT_SERIES) {
      expect(unsupportedSeries({ series: [{ type }] })).toEqual([])
    }
  })

  it("names a series it cannot draw instead of leaving an empty box", () => {
    expect(unsupportedSeries({ series: [{ type: "sankey" }] })).toEqual(["sankey"])
  })

  it("reads a single series object as well as a list", () => {
    expect(unsupportedSeries({ series: { type: "treemap" } })).toEqual(["treemap"])
  })

  it("names each unsupported series once, and ignores the ones it can draw", () => {
    const option = {
      series: [{ type: "line" }, { type: "sankey" }, { type: "sankey" }, { type: "graph" }],
    }

    expect(unsupportedSeries(option)).toEqual(["sankey", "graph"])
  })

  it("says nothing about an option with no series at all", () => {
    expect(unsupportedSeries({ title: { text: "empty" } })).toEqual([])
  })

  it("ignores entries that do not name a type", () => {
    expect(unsupportedSeries({ series: [{ data: [1, 2] }, null, "line"] })).toEqual([])
  })
})

describe("laying a chart out so its parts do not overlap", () => {
  it("puts a title at the top and the legend under it", () => {
    const laid = normalizeLayout({ title: { text: "Growth" }, legend: {} })

    expect(laid.title).toEqual({ left: "center", top: 0, text: "Growth" })
    expect(laid.legend).toEqual({ top: 28, left: "center" })
  })

  it("leaves room for a subtitle", () => {
    const laid = normalizeLayout({ title: { text: "Growth", subtext: "per second" }, legend: {} })

    expect(laid.legend).toMatchObject({ top: 44 })
  })

  it("keeps every position the document stated", () => {
    const laid = normalizeLayout({
      title: { text: "Growth", top: 8, left: "left" },
      legend: { bottom: 0 },
    })

    expect(laid.title).toMatchObject({ top: 8, left: "left" })
    expect(laid.legend).toEqual({ bottom: 0, left: "center" })
  })

  it("clears the plot of a cartesian chart below whatever is above it", () => {
    const laid = normalizeLayout({
      title: { text: "Growth" },
      legend: {},
      series: [{ type: "line" }],
    })

    expect(laid.grid).toEqual({ top: 72, containLabel: true })
  })

  it("does not move a plot that has no grid", () => {
    const laid = normalizeLayout({ title: { text: "Share" }, series: [{ type: "pie" }] })

    expect(laid.grid).toBeUndefined()
  })

  it("leaves an option with neither title nor legend alone", () => {
    const option = { series: [{ type: "bar", data: [1] }] }

    expect(normalizeLayout(option)).toEqual(option)
  })
})
