import { z } from "zod"

import { t } from "@/shared/i18n"

export const ROW_FIELD = "$row"

export const chartSpecSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("line"), x: z.string().min(1), y: z.string().min(1) }).strict(),
  z.object({ type: z.literal("bar"), x: z.string().min(1), y: z.string().min(1) }).strict(),
  z
    .object({
      type: z.literal("pie"),
      label: z.string().min(1),
      value: z.string().min(1),
    })
    .strict(),
])

export type ChartSpec = z.infer<typeof chartSpecSchema>
export type ChartType = ChartSpec["type"]

export function dimensionField(spec: ChartSpec): string {
  return spec.type === "pie" ? spec.label : spec.x
}

export function measureField(spec: ChartSpec): string {
  return spec.type === "pie" ? spec.value : spec.y
}

export function makeChartSpec(type: ChartType, dimension: string, measure: string): ChartSpec {
  return type === "pie"
    ? { type, label: dimension, value: measure }
    : { type, x: dimension, y: measure }
}

export function chartSpecKey(spec: ChartSpec): string {
  return `${spec.type}:${dimensionField(spec)}:${measureField(spec)}`
}

export function fieldLabel(field: string): string {
  return field === ROW_FIELD ? t("charts.row") : field
}
