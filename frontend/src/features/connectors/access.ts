import type { ConnectorPublic, GrantWrite } from "@/client"

/**
 * The scale of what a caller may do with a connection.
 *
 * Read off the generated client rather than written out again: the server owns
 * the vocabulary, and a level added there turns into a type error here instead
 * of a second list quietly falling behind. See D33.
 */
export type Access = ConnectorPublic["access"]

/** What may be given away. Ownership is not on this list. */
export type Grant = GrantWrite["access"]

const RANK: Record<Access, number> = { read: 0, write: 1, structure: 2, own: 3 }

/**
 * Whether a held level admits everything a required one does.
 *
 * The same comparison the server makes, and for a different purpose: there it
 * decides an answer, here it decides whether a button is worth showing. A
 * screen that guessed from the name of the level would be a second rule.
 */
export function atLeast(held: Access, required: Access): boolean {
  return RANK[held] >= RANK[required]
}

/** How a level reads on screen, in one place, so two screens cannot word it
 * differently. */
export const ACCESS_LABELS: Record<Access, string> = {
  read: "Read",
  write: "Edit rows",
  structure: "Change structure",
  own: "Owner",
}

/** What a grant may be set to, in the order of the scale. */
export const GRANT_OPTIONS: { label: string; value: Grant }[] = [
  { label: ACCESS_LABELS.read, value: "read" },
  { label: ACCESS_LABELS.write, value: "write" },
  { label: ACCESS_LABELS.structure, value: "structure" },
]
