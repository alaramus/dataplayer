import type { JsonContent } from "@/client"

export type JsonValue = NonNullable<JsonContent["value"]>

export function quoted(value: string): string {
  return JSON.stringify(value)
}

export function scalarText(value: JsonValue): string {
  if (value.kind === "null") return "null"
  if (value.kind === "string") return quoted(value.value ?? "")
  return value.value ?? ""
}
