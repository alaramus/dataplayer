/**
 * The ECharts option of a time-series widget, built without a chart.
 *
 * Lines are curved with `smoothMonotone: 'x'`: both control points of a
 * segment sit at the height of a real sample, so a curve through 0 % and 40 %
 * never dips below zero on the way.
 */

import type { EChartsOption } from "echarts"

import { formatDate, formatDateTime, formatTime } from "@/shared/i18n/format"

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
  /** The caption size of the scale, in pixels, read off --dp-font-size-xs. */
  size: number
  font: string
}

/**
 * A tick on the time axis. ECharts marks midnight with the day alone, a bare
 * "18" among the hours that read as a value, and its own Russian months are
 * capitalised ("Окт"); the interface's language writes «18 окт.».
 */
export function timeTick(value: number): string {
  const at = new Date(value)
  if (at.getHours() === 0 && at.getMinutes() === 0 && at.getSeconds() === 0) {
    return formatDate(at, { day: "numeric", month: "short" })
  }
  return formatTime(at, {
    hour: "2-digit",
    minute: "2-digit",
    ...(at.getSeconds() === 0 ? {} : { second: "2-digit" }),
    hourCycle: "h23",
  })
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
    if (typeof ts === "number" && when === "") when = formatDateTime(ts)
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
    // ECharts' own 12px axis and 13px legend, beside an 11px caption scale
    // and a 13px chrome: the widget's words in the scale's caption size and
    // face (D187).
    textStyle: { fontFamily: colours.font, fontSize: colours.size },
    grid: { left: 8, right: 12, top: series.length > 1 ? 28 : 12, bottom: 8, containLabel: true },
    legend: series.length > 1
      ? { type: "scroll", top: 0, textStyle: { color: colours.text, fontSize: colours.size } }
      : { show: false },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => tooltipLines(params, units),
    },
    xAxis: {
      type: "time",
      axisLabel: {
        color: colours.text,
        fontSize: colours.size,
        hideOverlap: true,
        formatter: timeTick,
      },
      axisLine: { lineStyle: { color: colours.grid } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        color: colours.text,
        fontSize: colours.size,
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
