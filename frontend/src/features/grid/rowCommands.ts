/**
 * Turning a selection of rows into what a source-declared command takes.
 *
 * A row command (D70) names one column as the thing that identifies a row —
 * `pid` for a list of server processes. The grid holds a page of text and a
 * set of selected row numbers, and this is the whole of the translation
 * between them. Nothing here is keyed by the name of a command: which column
 * to read comes from the answer that offered it.
 */

import type { FetchColumn, RowCommand } from "@/client"

import type { GridRow } from "./types"

/**
 * The keys of the selected rows, in the order they are on screen.
 *
 * Empty when the command names a column this page does not have — which is a
 * disagreement between the source's declaration and its own answer, and the
 * honest response to it is to offer nothing rather than to send the wrong
 * column. Blank cells are left out for the same reason.
 */
export function keysOf(
  command: RowCommand,
  columns: readonly FetchColumn[],
  rows: readonly GridRow[],
  selected: readonly number[]
): string[] {
  const at = columns.findIndex((column) => column.name === command.identified_by)
  if (at < 0) return []
  const seen = new Set<string>()
  for (const index of [...selected].sort((left, right) => left - right)) {
    const value = rows[index]?.values[at]
    // A row is named once however many of its cells are in the selection.
    if (typeof value === "string" && value !== "") seen.add(value)
  }
  return [...seen]
}

/** What a confirmation asks before a command that says it is destructive. */
export function commandQuestion(command: RowCommand, keys: readonly string[]): string {
  const count = keys.length
  return count === 1
    ? `${command.title} ${keys[0] ?? ""}?`
    : `${command.title} ${String(count)} rows?`
}

/**
 * What to say after one ran.
 *
 * The source's own sentence, with what it would not do added to it. Both come
 * from the answer; this only decides that a refusal is worth a line of its
 * own rather than being dropped because the count already implies it.
 */
export function commandOutcome(result: {
  message: string
  refused?: readonly string[] | null
}): { text: string; failed: boolean } {
  const refused = result.refused ?? []
  if (refused.length === 0) return { text: result.message, failed: false }
  return { text: `${result.message}. ${refused.join("; ")}`, failed: true }
}
