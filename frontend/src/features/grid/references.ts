import type { FetchColumn, FetchReference, ReferenceValue } from "@/client"

/**
 * Where the way out of a row is drawn, and what is sent when it is pressed.
 *
 * Both are decisions about the screen. What the key means — which of the
 * target's columns each of these stands for, whether an empty one names
 * anything, whether the target can be looked up at all — belongs to the source
 * and is never worked out here. See D36.
 */

/**
 * The references this column carries the handle for.
 *
 * One handle per reference and not per column: a composite key spans several
 * columns and is one way out, so the arrow sits on the first of its columns
 * that is actually on screen. Hiding that column moves the arrow to the next
 * one rather than taking the way out away.
 */
export function referencesLedBy(
  references: readonly FetchReference[],
  columnName: string,
  visibleColumns: readonly string[]
): FetchReference[] {
  const onScreen = new Set(visibleColumns)
  return references.filter(
    (reference) => reference.columns.find((name) => onScreen.has(name)) === columnName
  )
}

/**
 * What one row holds for every column of one reference.
 *
 * Every column of the key, whatever the row has in it — a missing value is
 * sent as null rather than left out, because what an absent key names is the
 * source's answer and not this file's guess. Nothing is returned at all when
 * the page does not carry one of the columns, which is a page read before the
 * relation changed.
 */
export function keyValues(
  reference: FetchReference,
  columns: readonly FetchColumn[],
  values: readonly (string | null)[]
): ReferenceValue[] | null {
  const taken: ReferenceValue[] = []
  for (const name of reference.columns) {
    const index = columns.findIndex((column) => column.name === name)
    if (index === -1) return null
    taken.push({ column: name, value: values[index] ?? null })
  }
  return taken
}
