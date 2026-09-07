/**
 * Turning one row of a page into what a source-declared command takes.
 *
 * A row command (D70) names one column as the thing that identifies a row —
 * `pid` for a list of server processes — and is offered in the corner of the
 * row it is about. The grid holds a page of text, and this is the whole of the
 * translation between the two. Nothing here is keyed by the name of a command:
 * which column names a row, and which rows a command belongs on, both come
 * from the answer that offered it.
 */

import type { FetchColumn, RowCommand } from "@/client"

import type { GridRow } from "./types"

/**
 * What this row is called, for this command.
 *
 * Null when the command names a column the page does not have — a
 * disagreement between the source's declaration and its own answer, where the
 * honest response is to offer nothing rather than to send the wrong column —
 * and null for a blank cell, which names no row.
 */
export function keyOf(
  command: RowCommand,
  columns: readonly FetchColumn[],
  row: GridRow
): string | null {
  const at = columns.findIndex((column) => column.name === command.identified_by)
  if (at < 0) return null
  const value = row.values[at]
  return typeof value === "string" && value !== "" ? value : null
}

/**
 * The commands offered on one row, in the order the source listed them.
 *
 * A command may say it belongs only on rows whose cell in one column holds one
 * value: an extension is installed or removed, never both, and the row already
 * says which. The comparison is against the cell exactly as the source's own
 * answer spelled it, so nothing here learns what `installed` means.
 */
export function commandsForRow(
  commands: readonly RowCommand[],
  columns: readonly FetchColumn[],
  row: GridRow
): RowCommand[] {
  return commands.filter((command) => {
    if (keyOf(command, columns, row) === null) return false
    const condition = command.applies_when
    if (condition === undefined || condition === null) return true
    const at = columns.findIndex((column) => column.name === condition.column)
    // The same disagreement as a missing key column, answered the same way.
    return at >= 0 && row.values[at] === condition.equals
  })
}

/** What a confirmation asks before a command that says it is destructive. */
export function commandQuestion(command: RowCommand, key: string): string {
  return `${command.title} ${key}?`
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
