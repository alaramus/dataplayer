import type { FetchColumn, KeyedChoice, PasteColumn } from "@/client"

/**
 * What a link keeping the latest per key starts with (D314), before anybody
 * chose: the key from a topic's `key`, and its JSON fields as a hash — or its
 * whole value as a string when it has no fields.
 */

const FIELD = "value."

/** The name a column is written under in a hash: a topic's field by its own name. */
export function fieldName(column: string): string {
  return column.startsWith(FIELD) && column.length > FIELD.length ? column.slice(FIELD.length) : column
}

export function defaultKey(columns: readonly FetchColumn[]): string | null {
  return (columns.find((column) => column.name === "key") ?? columns[0])?.name ?? null
}

export function defaultValues(columns: readonly FetchColumn[], key: string | null): PasteColumn[] {
  const fields = columns.filter((column) => column.name.startsWith(FIELD))
  if (fields.length > 0) return fields.map((column) => ({ source: column.name, target: fieldName(column.name) }))
  const value = columns.find((column) => column.name === "value") ?? columns.find((column) => column.name !== key)
  return value ? [{ source: value.name, target: fieldName(value.name) }] : []
}

export type KeyedPick = { byKey: KeyedChoice; columns: PasteColumn[] }

/** Whether the window's choice can be kept: a key, at least one value, field names unique and filled. */
export function keyedProblem(pick: KeyedPick): "key" | "values" | "names" | null {
  if (!pick.byKey.key_column) return "key"
  if (pick.columns.length === 0) return "values"
  const names = pick.columns.map((column) => column.target.trim())
  if (pick.columns.length > 1 && (names.some((name) => name === "") || new Set(names).size !== names.length)) {
    return "names"
  }
  return null
}

/** One value is a string, several are a hash. */
export function holdsHash(columns: readonly PasteColumn[]): boolean {
  return columns.length > 1
}
