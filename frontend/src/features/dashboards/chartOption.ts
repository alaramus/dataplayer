/**
 * The ECharts option of a time-series widget, built without a chart.
 *
 * Lines are curved with `smoothMonotone: 'x'`: both control points of a
 * segment sit at the height of a real sample, so a curve through 0 % and 40 %
 * never dips below zero on the way.
 */

import type { EChartsOption } from "echarts"

import { formatValue } from "./seriesFormat"

export interface ChartSeries {
  id: number
  name: string
  unit: string
  /** [ts, value] or [ts, avg, min, max], seconds; the value is at index 1. */
  points: readonly (readonly number[])[]
}

export interface ChartColours {
  palette: string[]
  text: string
  grid: string
}

export function sharedUnit(series: readonly ChartSeries[]): string | null {
  const units = new Set(series.map((one) => one.unit))
  return units.size === 1 ? ([...units][0] ?? null) : null
}

function tooltipLines(params: unknown, units: Map<string, string>): string {
  const items = Array.isArray(params) ? params : [params]
  const lines: string[] = []
  let when = ""
  for (const item of items) {
    if (typeof item !== "object" || item === null) continue
    const record = item as { seriesName?: unknown; value?: unknown; marker?: unknown }
    const value = Array.isArray(record.value) ? record.value : []
    const [ts, reading] = value as [unknown, unknown]
    if (typeof ts === "number" && when === "") when = new Date(ts).toLocaleString()
    if (typeof reading !== "number" || typeof record.seriesName !== "string") continue
    const marker = typeof record.marker === "string" ? record.marker : ""
    lines.push(`${marker}${record.seriesName}: ${formatValue(reading, units.get(record.seriesName) ?? "")}`)
  }
  return [when, ...lines].join("<br>")
}

export function timeseriesOption(series: readonly ChartSeries[], colours: ChartColours): EChartsOption {
  const unit = sharedUnit(series)
  const units = new Map(series.map((one) => [one.name, one.unit]))
  return {
    animation: false,
    backgroundColor: "transparent",
    color: colours.palette,
    grid: { left: 8, right: 12, top: series.length > 1 ? 28 : 12, bottom: 8, containLabel: true },
    legend: series.length > 1
      ? { type: "scroll", top: 0, textStyle: { color: colours.text } }
      : { show: false },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => tooltipLines(params, units),
    },
    xAxis: {
      type: "time",
      axisLabel: { color: colours.text, hideOverlap: true },
      axisLine: { lineStyle: { color: colours.grid } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: colours.text,
        formatter: (value: number) => formatValue(value, unit ?? ""),
      },
      splitLine: { lineStyle: { color: colours.grid } },
    },
    series: series.map((one) => ({
      type: "line" as const,
      name: one.name,
      showSymbol: false,
      smooth: true,
      smoothMonotone: "x" as const,
      sampling: "lttb" as const,
      data: one.points.map((point) => [(point[0] ?? 0) * 1000, point[1] ?? null]),
    })),
  }
}
