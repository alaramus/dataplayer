import type { ColumnType, FetchResult } from "@/client"

import type { GridRow } from "./types"

export function toGridRows(result: FetchResult, offset: number): GridRow[] {
  return result.rows.map((values, index) => ({
    id: String(offset + index),
    values,
  }))
}

export interface CellPresentation {
  text: string
  align: "left" | "right" | "center"
  tone: "default" | "null"
  monospace?: boolean
}

export function cellPresentation(
  value: string | null,
  type: ColumnType
): CellPresentation {
  if (value === null) return { text: "null", align: "left", tone: "default" }

  switch (type.category) {
    case "number":
      return { text: value, align: "right", tone: "default" }
    case "boolean":
      return { text: value, align: "center", tone: "default" }
    case "binary":
    case "uuid":
      return { text: value, align: "left", tone: "default", monospace: true }
    case "string":
    case "datetime":
    case "json":
    case "network":
    case "geometric":
    case "range":
    case "enum":
    case "composite":
    case "array":
    case "other":
      return { text: value, align: "left", tone: "default" }
    default:
      return assertNever(type.category)
  }
}

export function shouldOpenViewer(value: string | null, type: ColumnType): boolean {
  if (value === null) return false
  switch (type.category) {
    case "binary":
    case "json":
    case "array":
      return true
    case "number":
    case "boolean":
    case "datetime":
    case "uuid":
    case "network":
    case "geometric":
    case "range":
    case "enum":
    case "composite":
    case "other":
    case "string":
      return value.length > 120
    default:
      return assertNever(type.category)
  }
}

function assertNever(value: never): never {
  throw new Error(`Unsupported column category: ${String(value)}`)
}
