import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import { buildChart, isValidChartSpec, numericMeasureNames, suggestCharts } from "./model"
import { ROW_FIELD } from "./types"

const columns: FetchColumn[] = [
  { name: "day", type: { sql: "date", category: "datetime" } },
  { name: "team", type: { sql: "text", category: "string" } },
  { name: "amount", type: { sql: "numeric", category: "number" } },
]

const rows = [
  ["2026-08-01", "Core", "10"],
  ["2026-08-02", "Core", "5"],
  ["2026-08-03", "Research", "7"],
  ["bad-date", "Research", null],
]

describe("a bounded chart model", () => {
  it("suggests deterministic closed views from server-declared types", () => {
    expect(suggestCharts(columns, rows)).toEqual([
      { label: "amount over day", spec: { type: "line", x: "day", y: "amount" } },
      { label: "amount by team", spec: { type: "bar", x: "team", y: "amount" } },
      {
        label: "amount share by team",
        spec: { type: "pie", label: "team", value: "amount" },
      },
    ])
  })

  it("omits null and invalid values rather than turning them into zero", () => {
    const chart = buildChart({ type: "line", x: "day", y: "amount" }, columns, rows)
    expect(chart?.points).toBe(3)
  })

  it("aggregates repeated bar labels within this page", () => {
    const chart = buildChart({ type: "bar", x: "team", y: "amount" }, columns, rows)
    const option = chart?.option as { series: Array<{ data: number[] }> }
    expect(chart?.points).toBe(2)
    expect(option.series[0]?.data).toEqual([15, 7])
  })

  it("keeps lossless date text when a date is used as a category", () => {
    const chart = buildChart({ type: "bar", x: "day", y: "amount" }, columns, rows)
    const option = chart?.option as { xAxis: { data: string[] } }
    expect(option.xAxis.data[0]).toBe("2026-08-01")
  })

  it("omits negative pie observations", () => {
    const chart = buildChart({ type: "pie", label: "team", value: "amount" }, columns, [
      ...rows,
      ["2026-08-04", "Loss", "-3"],
    ])
    const option = chart?.option as {
      series: Array<{ data: Array<{ name: string; value: number }> }>
    }
    expect(option.series[0]?.data).toEqual([
      { name: "Core", value: 15 },
      { name: "Research", value: 7 },
    ])
  })

  it("does not suggest a pie when a positive category sum hides a negative row", () => {
    const withHiddenLoss = [
      ["2026-08-01", "Core", "10"],
      ["2026-08-02", "Core", "-2"],
      ["2026-08-03", "Research", "7"],
    ]
    expect(suggestCharts(columns, withHiddenLoss).map(({ spec }) => spec.type)).toEqual([
      "line",
      "bar",
    ])
  })

  it("keeps twelve pie slices and combines the rest", () => {
    const manyRows = Array.from({ length: 14 }, (_, index) => [
      `2026-08-${String(index + 1).padStart(2, "0")}`,
      `Team ${String(index + 1)}`,
      String(14 - index),
    ])
    const chart = buildChart({ type: "pie", label: "team", value: "amount" }, columns, manyRows)
    const option = chart?.option as {
      series: Array<{ data: Array<{ name: string; value: number }> }>
    }
    expect(option.series[0]?.data).toHaveLength(13)
    expect(option.series[0]?.data.at(-1)).toEqual({ name: "Other", value: 3 })
  })

  it("falls back to row number for one numeric column", () => {
    const numeric = [columns[2]!]
    expect(suggestCharts(numeric, [["4"], ["8"]])).toEqual([
      { label: "amount over Row", spec: { type: "line", x: ROW_FIELD, y: "amount" } },
    ])
  })

  it("refuses a non-numeric measure", () => {
    expect(isValidChartSpec({ type: "line", x: "day", y: "team" }, columns, rows)).toBe(false)
  })

  it("offers a wholly numeric CSV field without changing its source type", () => {
    const csvColumns: FetchColumn[] = [
      { name: "id", type: { sql: "text", category: "string" } },
      { name: "name", type: { sql: "text", category: "string" } },
      { name: "score", type: { sql: "text", category: "string" } },
    ]
    const csvRows = [
      ["1", "Ada", "12.5"],
      ["2", "Grace", "9"],
      ["3", "Linus", null],
    ]
    expect(numericMeasureNames(csvColumns, csvRows)).toEqual(new Set(["id", "score"]))
    expect(suggestCharts(csvColumns, csvRows)[0]).toEqual({
      label: "score by name",
      spec: { type: "bar", x: "name", y: "score" },
    })
  })

  it("does not guess a mixed CSV field is numeric", () => {
    const csvColumns: FetchColumn[] = [{ name: "value", type: { sql: "text", category: "string" } }]
    expect(numericMeasureNames(csvColumns, [["12"], ["unknown"]])).toEqual(new Set())
  })
})
