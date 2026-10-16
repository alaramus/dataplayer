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

import { t } from "@/shared/i18n"
import { appIcons } from "@/shared/ui/icons"

/** The groups, in the order they are drawn. */
export const TOOLBAR_GROUPS = [
  {
    name: "view",
    get label() {
      return t("grid.toolbar.groups.view")
    },
  },
  {
    name: "open",
    get label() {
      return t("grid.toolbar.groups.open")
    },
  },
  {
    name: "out",
    get label() {
      return t("grid.toolbar.groups.out")
    },
  },
  {
    name: "write",
    get label() {
      return t("grid.toolbar.groups.write")
    },
  },
  {
    name: "tab",
    get label() {
      return t("grid.toolbar.groups.tab")
    },
  },
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
  structure: {
    icon: appIcons.accountTree,
    get label() {
      return t("grid.toolbar.commands.structure")
    },
  },
  query: {
    icon: appIcons.terminal,
    get label() {
      return t("grid.toolbar.commands.query")
    },
  },
  document: {
    icon: appIcons.code,
    get label() {
      return t("grid.toolbar.commands.document")
    },
  },
  chart: {
    icon: appIcons.insertChart,
    get label() {
      return t("grid.toolbar.commands.chart")
    },
  },
  download: {
    icon: appIcons.download,
    get label() {
      return t("grid.toolbar.commands.download")
    },
  },
  share: {
    icon: appIcons.share,
    get label() {
      return t("grid.toolbar.commands.share")
    },
  },
  keep: {
    icon: appIcons.postAdd,
    get label() {
      return t("grid.toolbar.commands.keep")
    },
  },
  paste: {
    icon: appIcons.contentPaste,
    get label() {
      return t("grid.toolbar.commands.paste")
    },
  },
  import: {
    icon: appIcons.input,
    get label() {
      return t("grid.toolbar.commands.import")
    },
  },
  insert: {
    icon: appIcons.add,
    get label() {
      return t("grid.toolbar.commands.insert")
    },
  },
  remove: {
    icon: appIcons.remove,
    get label() {
      return t("grid.toolbar.commands.remove")
    },
  },
  refresh: {
    icon: appIcons.autorenew,
    get label() {
      return t("grid.toolbar.commands.refresh")
    },
  },
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
  get filter() {
    return t("grid.toolbar.not_offered.filter")
  },
  get sort() {
    return t("grid.toolbar.not_offered.sort")
  },
  get import() {
    return t("grid.toolbar.not_offered.import")
  },
  get paste() {
    return t("grid.toolbar.not_offered.paste")
  },
  get download() {
    return t("grid.toolbar.not_offered.download")
  },
  get share() {
    return t("grid.toolbar.not_offered.share")
  },
  get chart() {
    return t("grid.toolbar.not_offered.chart")
  },
  get keep() {
    return t("grid.toolbar.not_offered.keep")
  },
  get document() {
    return t("grid.toolbar.not_offered.document")
  },
  get query() {
    return t("grid.toolbar.not_offered.query")
  },
  get structure() {
    return t("grid.toolbar.not_offered.structure")
  },
  get insert() {
    return t("grid.toolbar.not_offered.insert")
  },
  get remove() {
    return t("grid.toolbar.not_offered.remove")
  },
} as const

/**
 * Why a query result offers what it does not: an arbitrary projection has no
 * row identity to act on and names no node of any source (D64).
 */
export const NOT_IN_A_RESULT = {
  get structure() {
    return t("grid.toolbar.not_in_result.structure")
  },
  get query() {
    return t("grid.toolbar.not_in_result.query")
  },
  get document() {
    return NOT_OFFERED.document
  },
  get share() {
    return t("grid.toolbar.not_in_result.share")
  },
  get keep() {
    return t("grid.toolbar.not_in_result.keep")
  },
  get paste() {
    return t("grid.toolbar.not_in_result.paste")
  },
  get import() {
    return t("grid.toolbar.not_in_result.import")
  },
  get insert() {
    return t("grid.toolbar.not_in_result.insert")
  },
  get remove() {
    return t("grid.toolbar.not_in_result.remove")
  },
  get refresh() {
    return t("grid.toolbar.not_in_result.refresh")
  },
} as const satisfies Partial<Record<GridCommand, string>>

/** And the ones that name something to do, rather than something to accept. */
export const NOT_YET = {
  get reading() {
    return t("grid.toolbar.not_yet.reading")
  },
  get unread() {
    return t("grid.toolbar.not_yet.unread")
  },
  get noRows() {
    return t("grid.toolbar.not_yet.no_rows")
  },
  get noColumns() {
    return t("grid.toolbar.not_yet.no_columns")
  },
  get noSelection() {
    return t("grid.toolbar.not_yet.no_selection")
  },
  get noRowsPicked() {
    return t("grid.toolbar.not_yet.no_rows_picked")
  },
  get noClipboard() {
    return t("grid.toolbar.not_yet.no_clipboard")
  },
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
