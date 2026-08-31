/**
 * What an `echarts` fence inside a document may draw.
 *
 * This is a wider vocabulary than the chart panel's (D35), and deliberately so:
 * a chart built over a connection's rows is composed by the application from a
 * closed set of choices, while a fence is a picture its author already drew.
 * The set is the one the documents this viewer was ported from actually use.
 * It is loaded with the block, not with the application.
 */
import {
  BarChart,
  FunnelChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  PieChart,
  RadarChart,
  ScatterChart,
} from "echarts/charts"
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components"
import { use } from "echarts/core"
import { SVGRenderer } from "echarts/renderers"

/** Series types this bundle can draw. Anything else is refused by name. */
export const DOCUMENT_SERIES = new Set([
  "bar",
  "funnel",
  "gauge",
  "heatmap",
  "line",
  "pie",
  "radar",
  "scatter",
])

export function registerDocumentCharts(): void {
  use([
    BarChart,
    FunnelChart,
    GaugeChart,
    HeatmapChart,
    LineChart,
    PieChart,
    RadarChart,
    ScatterChart,
    DataZoomComponent,
    GridComponent,
    LegendComponent,
    MarkLineComponent,
    MarkPointComponent,
    TitleComponent,
    ToolboxComponent,
    TooltipComponent,
    VisualMapComponent,
    SVGRenderer,
  ])
}

/**
 * Name the series a document asked for and this bundle cannot draw.
 *
 * ECharts reports an unregistered series to the console and then draws an
 * empty box, which reads as a bug in the document. Asking first turns that into
 * a sentence the reader can act on.
 */
export function unsupportedSeries(option: Record<string, unknown>): string[] {
  const series = option.series
  const entries = Array.isArray(series) ? series : series === undefined ? [] : [series]
  const named = entries
    .map((entry) =>
      typeof entry === "object" && entry !== null
        ? (entry as { type?: unknown }).type
        : undefined
    )
    .filter((type): type is string => typeof type === "string")
  return [...new Set(named.filter((type) => !DOCUMENT_SERIES.has(type)))]
}

/** Series drawn inside a cartesian grid, which needs clearance under a title. */
const GRID_SERIES = new Set(["bar", "heatmap", "line", "scatter"])

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * Stack the title, the legend and the plot so they do not sit on each other.
 *
 * A document names a chart's parts and rarely its geometry, and ECharts places
 * each part independently: a title and a legend both default to the top and
 * overlap. Here they are laid out in order, one under the other, and whatever
 * the document did state wins — this only fills in what was left unsaid.
 */
export function normalizeLayout(option: Record<string, unknown>): Record<string, unknown> {
  const laid: Record<string, unknown> = { ...option }
  let cursor = 0

  const title = isObject(option.title) ? option.title : null
  const titled = title !== null && (title.text !== undefined || title.subtext !== undefined)
  if (titled && title !== null) {
    laid.title = { left: "center", top: cursor, ...title }
    cursor += title.subtext === undefined ? 28 : 44
  }

  const legend = isObject(option.legend) ? { ...option.legend } : null
  if (legend !== null) {
    if (legend.top === undefined && legend.bottom === undefined) legend.top = cursor
    if (legend.left === undefined && legend.right === undefined) legend.left = "center"
    laid.legend = legend
    if (legend.top !== undefined && legend.bottom === undefined) cursor += 32
  }

  const series = Array.isArray(option.series) ? option.series : []
  const usesGrid = series.some(
    (entry) => isObject(entry) && typeof entry.type === "string" && GRID_SERIES.has(entry.type)
  )
  if (usesGrid && (titled || legend !== null)) {
    const given = Array.isArray(option.grid) ? option.grid[0] : option.grid
    laid.grid = { top: cursor + 12, containLabel: true, ...(isObject(given) ? given : {}) }
  }

  return laid
}
