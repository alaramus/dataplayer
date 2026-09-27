/**
 * The row of commands above a table: what it is made of, and what it says.
 *
 * Two rules live here rather than in the templates that draw them.
 *
 * A command is never hidden for want of support. It stays where it is, greyed,
 * and says why on hover — the same answer the command bar gives (D69), for the
 * same reason: a row that changes shape as somebody walks between a table and
 * a file is a row they have to read every time, and a button that moves is a
 * button nobody learns the place of.
 *
 * And the commands are grouped by what they act on, with a name over each
 * group. Twenty buttons in one undifferentiated run is what this replaces.
 */

import { appIcons } from "@/shared/ui/icons"

/** The groups, in the order they are drawn. */
export const TOOLBAR_GROUPS = [
  { name: "view", label: "The view" },
  { name: "open", label: "Read it as" },
  { name: "out", label: "Take it out" },
  { name: "write", label: "Change the rows" },
  { name: "tab", label: "This tab" },
] as const

export type ToolbarGroup = (typeof TOOLBAR_GROUPS)[number]["name"]

/**
 * The picture and the name of each command the row can hold.
 *
 * Read by the grid of a node and by the table of a query result, which draw
 * the same row: a result greys most of these out rather than leaving whole
 * groups empty, and the two must not drift apart in how a command looks.
 */
export const GRID_COMMANDS = {
  structure: { icon: appIcons.accountTree, label: "Structure" },
  query: { icon: appIcons.terminal, label: "Open as a query" },
  document: { icon: appIcons.code, label: "Open as a document" },
  chart: { icon: appIcons.insertChart, label: "Charts" },
  download: { icon: appIcons.download, label: "Download" },
  share: { icon: appIcons.share, label: "Share this view" },
  keep: { icon: appIcons.postAdd, label: "Keep these rows as a new table or file" },
  paste: { icon: appIcons.contentPaste, label: "Paste into the selection" },
  import: { icon: appIcons.input, label: "Bring rows in" },
  insert: { icon: appIcons.add, label: "Insert row" },
  remove: { icon: appIcons.remove, label: "Delete selected rows" },
  refresh: { icon: appIcons.autorenew, label: "Refresh automatically" },
} as const

export type GridCommand = keyof typeof GRID_COMMANDS

/**
 * Why a command cannot be used, or nothing when it can.
 *
 * Two kinds of answer, and the difference is the whole value of the sentence:
 * one names something the reader can do about it — tick a row, copy something
 * — and the other says the source will never offer this, so they can stop
 * looking. They are worded apart and drawn the same: two shades of grey in one
 * row is a distinction nobody compares.
 */
export type Unavailable = string | null

/** What the tooltip of one command reads as. */
export function tipOf(label: string, reason: Unavailable): string {
  return reason === null ? label : `${label} — ${reason}`
}

/**
 * The sentences themselves, in one place so they can be read together.
 *
 * Together, because their value is in being consistent: every one of them is
 * read by the same person in the same row, and a mixture of "unsupported",
 * "not available" and "cannot" reads as three different mechanisms.
 */
export const NOT_OFFERED = {
  filter: "this source does not filter rows",
  sort: "this source does not sort rows",
  import: "this source does not take rows from another one",
  paste: "this source does not change rows",
  download: "this source does not write rows out",
  share: "a view of this source cannot be shared",
  chart: "there is nothing here to chart",
  keep: "this source cannot keep rows as a new table",
  document: "this is not a document",
  query: "this source does not run queries",
  structure: "this source does not describe its structure",
  insert: "this source does not add rows",
  remove: "this source does not delete rows",
} as const

/**
 * Why a query result offers what it does not: an arbitrary projection has no
 * row identity to act on and names no node of any source (D64).
 */
export const NOT_IN_A_RESULT = {
  structure: "a query result is not a table",
  query: "this is the result of a query already",
  document: NOT_OFFERED.document,
  share: "a query result cannot be shared",
  keep: "a query result cannot be kept as a table",
  paste: "a query result cannot be changed",
  import: "a query result cannot be changed",
  insert: "a query result cannot be changed",
  remove: "a query result cannot be changed",
  refresh: "a query result is read again only by running the query",
} as const satisfies Partial<Record<GridCommand, string>>

/** And the ones that name something to do, rather than something to accept. */
export const NOT_YET = {
  reading: "nothing has been read yet",
  unread: "these rows could not be read",
  noRows: "there are no rows here",
  noColumns: "every column is hidden",
  noSelection: "select some cells first",
  noRowsPicked: "tick a row first",
  noClipboard: "copy some cells first",
} as const

/**
 * The reason a command is off, given what the source offers and what is going
 * on right now.
 *
 * Ordered: what the source cannot do at all outranks what is merely missing
 * this second, because the second answer would be a lie about the first — no
 * amount of ticking rows makes a CSV file delete one.
 */
export function reasonFor(
  supported: boolean,
  unsupportedSays: string,
  waitingSays: Unavailable = null
): Unavailable {
  if (!supported) return unsupportedSays
  return waitingSays
}
