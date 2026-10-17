import type { ColumnType, FetchResult } from "@/client"
import { t } from "@/shared/i18n"

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

/**
 * What a cell of this type takes, in the words of the person editing it.
 *
 * Shown beside the column's own type name in the cell editor, so the question
 * "what may I type here" is answered where it is asked rather than in the
 * dialog's title.
 */
export function inputHint(type: ColumnType): string {
  switch (type.category) {
    case "number":
      return t("grid.input_hint.number")
    case "boolean":
      return t("grid.input_hint.boolean")
    case "datetime":
      return t("grid.input_hint.datetime")
    case "enum":
      return t("grid.input_hint.enum", { values: (type.enum_values ?? []).join(", ") })
    case "json":
      return "JSON"
    case "array":
      return t("grid.input_hint.array")
    case "uuid":
      return t("grid.input_hint.uuid")
    case "binary":
      return t("grid.input_hint.binary")
    case "network":
      return t("grid.input_hint.network")
    case "string":
      return t("grid.input_hint.string")
    case "geometric":
    case "range":
    case "composite":
    case "other":
      return t("grid.input_hint.other")
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
