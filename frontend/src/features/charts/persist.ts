import type { ChartSpec } from "./types"
import { chartSpecSchema } from "./types"

const PREFIX = "dataplayer-chart-view:"

export function chartStorageKey(viewKey: string): string {
  return `${PREFIX}${viewKey}`
}

export function loadChartSpec(viewKey: string): ChartSpec | null {
  const raw = localStorage.getItem(chartStorageKey(viewKey))
  if (raw === null) return null
  try {
    const parsed = chartSpecSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data : null
  } catch {
    return null
  }
}

export function saveChartSpec(viewKey: string, spec: ChartSpec): void {
  localStorage.setItem(chartStorageKey(viewKey), JSON.stringify(spec))
}

/** Move a client-only choice with the source-issued replacement identity. */
export function moveChartSpec(oldViewKey: string, newViewKey: string): void {
  if (oldViewKey === newViewKey) return
  const raw = localStorage.getItem(chartStorageKey(oldViewKey))
  if (raw !== null) localStorage.setItem(chartStorageKey(newViewKey), raw)
  localStorage.removeItem(chartStorageKey(oldViewKey))
}
