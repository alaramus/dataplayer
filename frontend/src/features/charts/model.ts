import type { EChartsOption } from "echarts"

import type { FetchColumn } from "@/client"
import { t } from "@/shared/i18n"

import { ROW_FIELD, chartSpecKey, dimensionField, fieldLabel, measureField } from "./types"
import type { ChartSpec } from "./types"

export interface BuiltChart {
  option: EChartsOption
  points: number
}

export interface ChartSuggestion {
  label: string
  spec: ChartSpec
}

const PAGE_NUMERIC_CATEGORIES = new Set(["string", "enum", "other"])

function indexOf(columns: readonly FetchColumn[], name: string): number {
  return columns.findIndex((column) => column.name === name)
}

function finiteNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined || value.trim() === "") return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Measures the source names as numbers, plus text that is wholly numeric on
 * this explicitly bounded page. The latter is a presentation fact, not a
 * claim that changes the source's declared column type.
 */
export function numericMeasureNames(
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[]
): Set<string> {
  const measures = new Set<string>()
  for (const [index, column] of columns.entries()) {
    if (column.type.category === "number") {
      measures.add(column.name)
      continue
    }
    if (!PAGE_NUMERIC_CATEGORIES.has(column.type.category)) continue
    let seen = false
    let numeric = true
    for (const row of rows) {
      const value = row[index]
      if (value === null || value === undefined || value.trim() === "") continue
      seen = true
      if (finiteNumber(value) === null) {
        numeric = false
        break
      }
    }
    if (seen && numeric) measures.add(column.name)
  }
  return measures
}

function rowDimension(
  row: readonly (string | null)[],
  rowIndex: number,
  columns: readonly FetchColumn[],
  field: string,
  offset: number
): string | number | null {
  if (field === ROW_FIELD) return offset + rowIndex + 1
  const index = indexOf(columns, field)
  if (index < 0) return null
  const value = row[index]
  if (value === null || value === undefined) return null
  const column = columns[index]
  if (column?.type.category === "number") return finiteNumber(value)
  if (column?.type.category === "datetime") {
    const timestamp = Date.parse(value)
    return Number.isFinite(timestamp) ? timestamp : null
  }
  return value
}

function categoryDimension(
  row: readonly (string | null)[],
  rowIndex: number,
  columns: readonly FetchColumn[],
  field: string,
  offset: number
): string | number | null {
  if (field === ROW_FIELD) return offset + rowIndex + 1
  const index = indexOf(columns, field)
  return index < 0 ? null : (row[index] ?? null)
}

function lineChart(
  spec: Extract<ChartSpec, { type: "line" }>,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset: number
): BuiltChart | null {
  const yIndex = indexOf(columns, spec.y)
  if (yIndex < 0) return null
  const xColumn = columns[indexOf(columns, spec.x)]
  const continuous =
    spec.x === ROW_FIELD ||
    xColumn?.type.category === "number" ||
    xColumn?.type.category === "datetime"

  if (continuous) {
    const data = rows.flatMap((row, rowIndex) => {
      const x = rowDimension(row, rowIndex, columns, spec.x, offset)
      const y = finiteNumber(row[yIndex])
      return x === null || y === null ? [] : [[x, y] as [string | number, number]]
    })
    if (data.length === 0) return null
    return {
      points: data.length,
      option: {
        animationDuration: 200,
        tooltip: { trigger: "axis" },
        grid: { left: 58, right: 24, top: 24, bottom: 52 },
        xAxis: {
          type: xColumn?.type.category === "datetime" ? "time" : "value",
          name: fieldLabel(spec.x),
          nameLocation: "middle",
          nameGap: 34,
        },
        yAxis: { type: "value", name: spec.y },
        series: [{ type: "line", name: spec.y, data, showSymbol: data.length < 80 }],
      },
    }
  }

  const labels: string[] = []
  const values: Array<number | null> = []
  let points = 0
  for (const [rowIndex, row] of rows.entries()) {
    const x = rowDimension(row, rowIndex, columns, spec.x, offset)
    if (x === null) continue
    const y = finiteNumber(row[yIndex])
    labels.push(String(x))
    values.push(y)
    if (y !== null) points += 1
  }
  if (points === 0) return null
  return {
    points,
    option: {
      animationDuration: 200,
      tooltip: { trigger: "axis" },
      grid: { left: 58, right: 24, top: 24, bottom: 72 },
      xAxis: {
        type: "category",
        data: labels,
        name: fieldLabel(spec.x),
        nameLocation: "middle",
        nameGap: 52,
        axisLabel: {
          hideOverlap: true,
          rotate: labels.some((label) => label.length > 12) ? 30 : 0,
        },
      },
      yAxis: { type: "value", name: spec.y },
      series: [{ type: "line", name: spec.y, data: values, showSymbol: points < 80 }],
    },
  }
}

function aggregate(
  dimension: string,
  measure: string,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset: number,
  nonNegative: boolean
): Map<string, number> {
  const measureIndex = indexOf(columns, measure)
  const result = new Map<string, number>()
  if (measureIndex < 0) return result
  for (const [rowIndex, row] of rows.entries()) {
    const label = categoryDimension(row, rowIndex, columns, dimension, offset)
    const value = finiteNumber(row[measureIndex])
    if (label === null || value === null || (nonNegative && value < 0)) continue
    const key = String(label)
    result.set(key, (result.get(key) ?? 0) + value)
  }
  return result
}

function barChart(
  spec: Extract<ChartSpec, { type: "bar" }>,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset: number
): BuiltChart | null {
  const values = aggregate(spec.x, spec.y, columns, rows, offset, false)
  if (values.size === 0) return null
  const labels = [...values.keys()]
  return {
    points: values.size,
    option: {
      animationDuration: 200,
      tooltip: { trigger: "axis" },
      grid: { left: 58, right: 24, top: 24, bottom: 72 },
      xAxis: {
        type: "category",
        data: labels,
        name: fieldLabel(spec.x),
        nameLocation: "middle",
        nameGap: 52,
        axisLabel: {
          hideOverlap: true,
          rotate: labels.some((label) => label.length > 12) ? 30 : 0,
        },
      },
      yAxis: { type: "value", name: spec.y },
      series: [{ type: "bar", name: spec.y, data: [...values.values()] }],
    },
  }
}

function pieChart(
  spec: Extract<ChartSpec, { type: "pie" }>,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset: number
): BuiltChart | null {
  const aggregated = aggregate(spec.label, spec.value, columns, rows, offset, true)
  if (aggregated.size === 0) return null
  const ranked = [...aggregated.entries()].sort((left, right) => right[1] - left[1])
  const visible = ranked.slice(0, 12).map(([name, value]) => ({ name, value }))
  const remainder = ranked.slice(12).reduce((sum, [, value]) => sum + value, 0)
  if (remainder > 0) visible.push({ name: t("charts.other"), value: remainder })
  return {
    points: aggregated.size,
    option: {
      animationDuration: 200,
      tooltip: { trigger: "item" },
      legend: { type: "scroll", orient: "vertical", right: 8, top: 20, bottom: 20 },
      series: [
        {
          type: "pie",
          name: spec.value,
          radius: ["34%", "68%"],
          center: ["42%", "52%"],
          data: visible,
          label: { formatter: "{b}: {d}%" },
        },
      ],
    },
  }
}

export function buildChart(
  spec: ChartSpec,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset = 0
): BuiltChart | null {
  switch (spec.type) {
    case "line":
      return lineChart(spec, columns, rows, offset)
    case "bar":
      return barChart(spec, columns, rows, offset)
    case "pie":
      return pieChart(spec, columns, rows, offset)
  }
}

export function isValidChartSpec(
  spec: ChartSpec,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[]
): boolean {
  const known = new Set(columns.map((column) => column.name))
  const dimension = dimensionField(spec)
  const measures = numericMeasureNames(columns, rows)
  return (dimension === ROW_FIELD || known.has(dimension)) && measures.has(measureField(spec))
}

function pieIsUseful(
  dimension: string,
  measure: string,
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset: number
): boolean {
  const measureIndex = indexOf(columns, measure)
  if (measureIndex < 0) return false
  for (const row of rows) {
    const value = finiteNumber(row[measureIndex])
    if (value !== null && value < 0) return false
  }
  const values = aggregate(dimension, measure, columns, rows, offset, false)
  return values.size >= 2
}

function identifierLike(name: string): boolean {
  const normal = name.toLowerCase()
  return normal === "id" || normal.endsWith("_id")
}

export function suggestCharts(
  columns: readonly FetchColumn[],
  rows: readonly (readonly (string | null)[])[],
  offset = 0
): ChartSuggestion[] {
  const measureNames = numericMeasureNames(columns, rows)
  const measures = columns
    .filter((column) => measureNames.has(column.name))
    .sort((left, right) => Number(identifierLike(left.name)) - Number(identifierLike(right.name)))
  const measure = measures[0]
  if (measure === undefined) return []

  const datetime = columns.find((column) => column.type.category === "datetime")
  const category = columns.find(
    (column) =>
      column.name !== measure.name &&
      !measureNames.has(column.name) &&
      column.type.category !== "datetime"
  )
  const secondNumber = measures.find((column) => column.name !== measure.name)
  const lineDimension = datetime?.name ?? category?.name ?? secondNumber?.name ?? ROW_FIELD
  const suggestions: ChartSuggestion[] = []

  if (datetime !== undefined) {
    suggestions.push({
      label: t("charts.suggestions.over", { measure: measure.name, dimension: datetime.name }),
      spec: { type: "line", x: datetime.name, y: measure.name },
    })
  }
  if (category !== undefined) {
    suggestions.push({
      label: t("charts.suggestions.by", { measure: measure.name, dimension: category.name }),
      spec: { type: "bar", x: category.name, y: measure.name },
    })
    if (pieIsUseful(category.name, measure.name, columns, rows, offset)) {
      suggestions.push({
        label: t("charts.suggestions.share", { measure: measure.name, dimension: category.name }),
        spec: { type: "pie", label: category.name, value: measure.name },
      })
    }
  }
  if (suggestions.length === 0 || datetime === undefined) {
    suggestions.push({
      label: t("charts.suggestions.over", {
        measure: measure.name,
        dimension: fieldLabel(lineDimension),
      }),
      spec: { type: "line", x: lineDimension, y: measure.name },
    })
  }

  const seen = new Set<string>()
  return suggestions.filter(({ spec }) => {
    const key = chartSpecKey(spec)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}
