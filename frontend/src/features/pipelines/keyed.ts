import type { KeyedChoice, PasteColumn } from "@/client"

/**
 * A link keeping the latest per key (D314), as its window shapes it. What it
 * starts with before anybody chose is the server's (D364).
 */

const FIELD = "value."

/** The name a column is written under in a hash: a topic's field by its own name. */
export function fieldName(column: string): string {
  return column.startsWith(FIELD) && column.length > FIELD.length ? column.slice(FIELD.length) : column
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
