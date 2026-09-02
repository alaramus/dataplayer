/**
 * A grid that re-reads itself, and how often.
 *
 * Everything here is a plain function so the parts worth arguing about — what
 * is offered, what is remembered, and when a tick must be skipped — can be
 * tested without a timer and without mounting a grid. The timer itself belongs
 * to the component that owns the fetch.
 *
 * The pause is the interesting half. Polling a relation while somebody is
 * typing into one of its cells would throw the typing away, and polling a tab
 * nobody is looking at spends a round trip per tab per interval. So a tick is
 * not "fetch now" but "fetch unless something says not to", and what says not
 * to is one list, in one place, that a tooltip can also read out.
 */

import { z } from "zod"

/** The intervals offered. Off is the absence of one, not a seventh entry. */
export const REFRESH_SECONDS = [1, 5, 10, 30, 60, 300] as const

export type RefreshSeconds = (typeof REFRESH_SECONDS)[number]

const refreshSecondsSchema = z.union([
  z.literal(1),
  z.literal(5),
  z.literal(10),
  z.literal(30),
  z.literal(60),
  z.literal(300),
])

/** How an interval is written on the button and in the menu. */
export function refreshLabel(seconds: RefreshSeconds): string {
  if (seconds < 60) return `${String(seconds)} s`
  const minutes = seconds / 60
  return `${String(minutes)} min`
}

/** The name a menu item is reported by, and what a test addresses it as. */
export function refreshItemName(seconds: RefreshSeconds | null): string {
  return seconds === null ? "off" : `s${String(seconds)}`
}

/** The interval a menu item name refers to, or undefined for a name of none. */
export function refreshSecondsOf(name: string): RefreshSeconds | null | undefined {
  if (name === "off") return null
  const found = REFRESH_SECONDS.find((seconds) => refreshItemName(seconds) === name)
  return found
}

/** What is stopping a tick from re-reading the page, in the user's words. */
export interface RefreshHold {
  /** A read is already under way; a second one would queue behind it. */
  fetching: boolean
  /** A cell is open in the editor, and its value is not saved. */
  editing: boolean
  /** A row is being written in the grid and has not been sent. */
  inserting: boolean
  /**
   * Rows are ticked.
   *
   * A selection is somebody about to do something to those rows, and a page
   * that arrives underneath it takes it away — which on a list of processes
   * means the row you meant to terminate is no longer the row you ticked.
   */
  selecting: boolean
  /** The tab is not on screen: another tab of this section, or another window. */
  away: boolean
}

/**
 * Why the page is not being re-read, or nothing when it is.
 *
 * One function for two callers: the tick asks it whether to fetch, and the
 * button asks it what to say. A held tick is skipped rather than queued —
 * the next one is at most an interval away, and a queue of them would all
 * land at once when the editor closes.
 */
export function refreshHeldBy(hold: RefreshHold): string | null {
  if (hold.editing) return "while a cell is being edited"
  if (hold.inserting) return "while a row is being written"
  if (hold.selecting) return "while rows are selected"
  if (hold.away) return "while this tab is not on screen"
  if (hold.fetching) return "while the last read is still running"
  return null
}

export function refreshTooltip(
  seconds: RefreshSeconds | null,
  held: string | null
): string {
  if (seconds === null) return "Refresh automatically"
  const every = `Refreshing every ${refreshLabel(seconds)}`
  return held === null ? every : `${every}, paused ${held}`
}

const KEY_PREFIX = "dataplayer:grid:refresh"

function refreshKey(connectorId: string, nodeId: string): string {
  return `${KEY_PREFIX}:${JSON.stringify([connectorId, nodeId])}`
}

/**
 * What this relation was last left refreshing at, if anybody ever said.
 *
 * Remembered per relation, like the columns and the query beside it: a table
 * watched every five seconds yesterday is one somebody is watching.
 *
 * Three answers, not two. `undefined` is nobody has ever chosen for this
 * relation, and `null` is somebody chose Off — which have to be told apart
 * now that a source may suggest an interval of its own (D70). Collapsing
 * them would turn off into "no opinion" and put the suggestion back the next
 * time the tab was opened, which is a grid refusing to stay stopped.
 *
 * A stored value that is not an offered interval is discarded rather than
 * trusted, because the offered set is allowed to change.
 */
export function loadRefreshSeconds(
  connectorId: string,
  nodeId: string
): RefreshSeconds | null | undefined {
  const raw = localStorage.getItem(refreshKey(connectorId, nodeId))
  if (raw === null) return undefined
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return undefined
  }
  if (parsed === null) return null
  const result = refreshSecondsSchema.safeParse(parsed)
  return result.success ? result.data : undefined
}

export function saveRefreshSeconds(
  connectorId: string,
  nodeId: string,
  seconds: RefreshSeconds | null
): void {
  localStorage.setItem(refreshKey(connectorId, nodeId), JSON.stringify(seconds))
}

/**
 * What a grid starts refreshing at when it opens a relation.
 *
 * A person's own choice wins, always. Only where there is none does the
 * source's suggestion apply: a list of server processes is about what is
 * happening this second and says so, while a table of invoices says nothing
 * and is left alone.
 */
export function startingRefresh(
  stored: RefreshSeconds | null | undefined,
  suggested: number | null | undefined
): RefreshSeconds | null {
  if (stored !== undefined) return stored
  return offeredNearest(suggested)
}

/**
 * The offered interval a suggestion becomes.
 *
 * The shortest one that is not shorter than what was asked for, because
 * polling a source faster than it asked to be polled is the one direction
 * that costs it something. A suggestion longer than anything offered takes
 * the longest.
 */
function offeredNearest(suggested: number | null | undefined): RefreshSeconds | null {
  if (suggested === null || suggested === undefined || suggested <= 0) return null
  return REFRESH_SECONDS.find((seconds) => seconds >= suggested) ?? 300
}
