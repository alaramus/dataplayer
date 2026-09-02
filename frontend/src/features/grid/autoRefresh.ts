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
 * What this relation was last left refreshing at.
 *
 * Remembered per relation, like the columns and the query beside it: a table
 * watched every five seconds yesterday is one somebody is watching. A stored
 * value that is not an offered interval is discarded rather than trusted,
 * because the offered set is allowed to change.
 */
export function loadRefreshSeconds(
  connectorId: string,
  nodeId: string
): RefreshSeconds | null {
  const raw = localStorage.getItem(refreshKey(connectorId, nodeId))
  if (raw === null) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  const result = refreshSecondsSchema.safeParse(parsed)
  return result.success ? result.data : null
}

export function saveRefreshSeconds(
  connectorId: string,
  nodeId: string,
  seconds: RefreshSeconds | null
): void {
  const key = refreshKey(connectorId, nodeId)
  // Off is the absence of an entry rather than a stored null: a relation
  // nobody ever watched and one somebody stopped watching are the same state.
  if (seconds === null) localStorage.removeItem(key)
  else localStorage.setItem(key, JSON.stringify(seconds))
}
