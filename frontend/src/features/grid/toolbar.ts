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
