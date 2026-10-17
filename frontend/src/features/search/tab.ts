import type { Hit } from "@/client"
import { t } from "@/shared/i18n"
import type { SelectOption } from "@/shared/ui"

import { groupsOf } from "./answer"
import type { AnswerState, CellState } from "./answer"
import { isObjectType, objectLabel } from "./kinds"
import { saidOf } from "./outcomes"
import type { Said } from "./outcomes"

/**
 * What the Search tab draws of an answer, and how its filters narrow it
 * (D205). Pure, so what is on screen at each line of a stream is tested
 * without one.
 */
export type ChangedWithin = "any" | "day" | "week" | "month" | "year"

export interface TabFilters {
  group: string | null
  connection: string | null
  kind: string | null
  changed: ChangedWithin
}

export const NO_FILTERS: TabFilters = { group: null, connection: null, kind: null, changed: "any" }

const DAY_MS = 24 * 60 * 60 * 1000

const WITHIN_MS: Record<Exclude<ChangedWithin, "any">, number> = {
  day: DAY_MS,
  week: 7 * DAY_MS,
  month: 30 * DAY_MS,
  year: 365 * DAY_MS,
}

export const CHANGED_OPTIONS: SelectOption[] = [
  // Short enough for the four filters to share a line; the select's own name,
  // "Changed", says which date it is.
  // Labels are getters, read when the select draws them.
  ...(["any", "day", "week", "month", "year"] as const).map((value) => ({
    get label() {
      return t(`search.changed.${value}`)
    },
    value,
  })),
]

/** The connection a hit is in, or is; nothing for what the application keeps. */
export function connectionOf(hit: Hit): string | null {
  return hit.target.kind === "object" ? null : hit.target.connector_id
}

/**
 * Whether a hit survives the filters on what it is. A thing that does not say
 * when it changed is left out once a time is chosen: it cannot be shown to
 * have changed then.
 */
export function passes(hit: Hit, filters: TabFilters, now: number): boolean {
  if (filters.connection !== null && connectionOf(hit) !== filters.connection) return false
  if (filters.kind !== null && hit.facts.kind !== filters.kind) return false
  if (filters.changed !== "any") {
    if (hit.facts.changed_at === null) return false
    const at = Date.parse(hit.facts.changed_at)
    if (Number.isNaN(at) || now - at > WITHIN_MS[filters.changed]) return false
  }
  return true
}

export interface SaidCell {
  cell: CellState
  said: Said
}

export interface TabGroup {
  key: string
  title: string
  connectorId: string | null
  hits: Hit[]
  /** Some cell of it is still being asked. */
  pending: boolean
  /** What its cells say about themselves: what was not searched, and why. */
  said: SaidCell[]
}

function saidOfCells(cells: readonly CellState[]): SaidCell[] {
  return cells.flatMap((cell) => {
    if (cell.outcome === null) return []
    const said = saidOf(cell.outcome, cell.planned)
    return said === null ? [] : [{ cell, said }]
  })
}

/**
 * The groups the tab draws, in the plan's fixed order (D202).
 *
 * A filter narrows what was found; what happened to each place it leaves
 * standing stays said. A group is drawn while it is being asked, when it
 * found something the filters keep, or when it has something to say — a
 * group that looked everywhere and found nothing is not drawn.
 */
export function tabGroups(state: AnswerState, filters: TabFilters, now: number): TabGroup[] {
  return groupsOf(state)
    .filter((group) => filters.group === null || group.key === filters.group)
    .filter(
      (group) =>
        filters.connection === null ||
        group.connectorId === filters.connection ||
        group.hits.some((hit) => connectionOf(hit) === filters.connection)
    )
    .map((group) => ({
      key: group.key,
      title: group.title,
      connectorId: group.connectorId,
      hits: group.hits.filter((hit) => passes(hit, filters, now)),
      pending: group.pending,
      said: saidOfCells(group.cells),
    }))
    .filter((group) => group.hits.length > 0 || group.pending || group.said.length > 0)
}

/** "Postgres", "Saved query": a kind as a person reads it. */
export function kindLabel(kind: string): string {
  if (isObjectType(kind)) return objectLabel(kind)
  const spaced = kind.replace(/[_-]+/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export interface FilterChoices {
  groups: SelectOption[]
  connections: SelectOption[]
  kinds: SelectOption[]
}

/** What each filter may be set to: only what this answer holds. */
export function filterChoices(state: AnswerState): FilterChoices {
  const shown = tabGroups(state, NO_FILTERS, 0)
  const connections = new Map<string, string>()
  const kinds = new Map<string, string>()
  for (const group of shown) {
    if (group.connectorId !== null) connections.set(group.connectorId, group.title)
    for (const hit of group.hits) {
      if (hit.target.kind === "connection" && !connections.has(hit.target.connector_id)) {
        connections.set(hit.target.connector_id, hit.title)
      }
      kinds.set(hit.facts.kind, kindLabel(hit.facts.kind))
    }
  }
  const byLabel = (a: SelectOption, b: SelectOption) => a.label.localeCompare(b.label)
  return {
    groups: shown.map((group) => ({ label: group.title, value: group.key })),
    connections: [...connections].map(([value, label]) => ({ label, value })).sort(byLabel),
    kinds: [...kinds].map(([value, label]) => ({ label, value })).sort(byLabel),
  }
}

/** "12 found", "1 found": the count the tab heads its answer with. */
export function foundCount(state: AnswerState): number {
  return groupsOf(state).reduce((total, group) => total + group.hits.length, 0)
}
