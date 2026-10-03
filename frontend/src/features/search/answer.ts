import type { EndLine, Hit, Outcome, PlanLine, PlannedCell } from "@/client"

import type { SearchLine } from "./stream"

/**
 * One answer, as its lines have built it so far (D201).
 *
 * Pure: a line in, the next state out, so what a screen draws at each moment
 * of a stream can be tested without one. The plan names every cell before
 * anything is found, so every group has its place from the first line, and a
 * cell that finishes late fills that place without moving anything drawn.
 */
export interface CellState {
  planned: PlannedCell
  /** Null while it is still being asked. */
  outcome: Outcome | null
  hits: Hit[]
}

export interface AnswerState {
  mode: PlanLine["mode"] | null
  /** Every cell of the plan, in the plan's order. */
  cells: CellState[]
  /** The best name matches: sent once, never reordered (D202). */
  best: Hit[] | null
  end: EndLine | null
}

export const EMPTY_ANSWER: AnswerState = { mode: null, cells: [], best: null, end: null }

function withCell(state: AnswerState, key: string, outcome: Outcome, hits: Hit[]): AnswerState {
  if (!state.cells.some((cell) => cell.planned.key === key)) return state
  return {
    ...state,
    cells: state.cells.map((cell) =>
      cell.planned.key === key ? { ...cell, outcome, hits } : cell
    ),
  }
}

/** The answer with one more line of its own stream in it. */
export function reduceAnswer(state: AnswerState, line: SearchLine): AnswerState {
  switch (line.type) {
    case "plan":
      return {
        mode: line.mode,
        cells: line.cells.map((planned) => ({ planned, outcome: null, hits: [] })),
        best: null,
        end: null,
      }
    case "cell":
      return withCell(state, line.key, line.outcome, line.hits)
    case "best":
      return state.best === null ? { ...state, best: line.hits } : state
    case "end":
      return { ...state, end: line }
  }
}

/**
 * The answer with a line of a follow-up in it: one cell asked again — Try
 * again, Search anyway, More in this connection — or the cells not asked.
 *
 * Its cells go back to pending in their places and keep what they had found
 * until their new line replaces it. Its best matches are not taken: those of
 * the answer were sent once and stay. Its end says nothing about the whole.
 */
export function reduceFollow(state: AnswerState, line: SearchLine): AnswerState {
  switch (line.type) {
    case "plan": {
      const known = new Set(state.cells.map((cell) => cell.planned.key))
      const asked = new Set(line.cells.map((planned) => planned.key))
      return {
        ...state,
        cells: [
          ...state.cells.map((cell) =>
            asked.has(cell.planned.key) ? { ...cell, outcome: null } : cell
          ),
          ...line.cells
            .filter((planned) => !known.has(planned.key))
            .map((planned) => ({ planned, outcome: null, hits: [] })),
        ],
      }
    }
    case "cell":
      return withCell(state, line.key, line.outcome, line.hits)
    case "best":
    case "end":
      return state
  }
}

/**
 * The cells a follow-up asked and never heard back about — it was refused,
 * cut off, or ended by a newer one — as they were before it. A cell it added
 * that was not in the answer goes again.
 */
export function settleFollow(
  before: AnswerState,
  after: AnswerState,
  asked: ReadonlySet<string>
): AnswerState {
  const was = new Map(before.cells.map((cell) => [cell.planned.key, cell]))
  return {
    ...after,
    cells: after.cells.flatMap((cell) => {
      if (cell.outcome !== null || !asked.has(cell.planned.key)) return [cell]
      const previous = was.get(cell.planned.key)
      return previous === undefined ? [] : [previous]
    }),
  }
}

/** What a cell says when the person stopped the search before it answered. */
export const STOPPED_BEFORE_ANSWER = "Stopped before it answered"

/**
 * The answer as it stood when the person stopped it: a cell still being asked
 * says it was stopped, and offers to be asked again, rather than being
 * drawn as still searching for ever.
 */
export function stopPending(state: AnswerState): AnswerState {
  return {
    ...state,
    cells: state.cells.map((cell) =>
      cell.outcome !== null
        ? cell
        : {
            ...cell,
            outcome: {
              way: "none",
              status: "failed",
              reason: null,
              notice: null,
              error_kind: null,
              message: STOPPED_BEFORE_ANSWER,
              more: false,
              as_of: null,
              deadline_seconds: null,
              since: null,
              owned: false,
            },
          }
    ),
  }
}

export interface GroupView {
  key: string
  title: string
  rank: number
  /** The connection a group is about, for the gestures and the filters. */
  connectorId: string | null
  hits: Hit[]
  /** Some cell of it is still being asked. */
  pending: boolean
  cells: CellState[]
}

/**
 * The groups in their fixed order (D202), each with its hits, once.
 *
 * Every group of the plan is here from the first line, empty or not, so a
 * screen can keep its place; drawing an empty one or not is the screen's
 * choice. A thing found twice is kept where it was found first, and hits in
 * `leaveOut` — the best matches, in the field — are not repeated.
 */
export function groupsOf(state: AnswerState, leaveOut: ReadonlySet<string> = new Set()): GroupView[] {
  const groups = new Map<string, GroupView>()
  for (const cell of state.cells) {
    const group = cell.planned.group
    let view = groups.get(group.key)
    if (view === undefined) {
      view = {
        key: group.key,
        title: group.title,
        rank: group.rank,
        connectorId: cell.planned.connector_id ?? null,
        hits: [],
        pending: false,
        cells: [],
      }
      groups.set(group.key, view)
    }
    view.cells.push(cell)
    view.pending = view.pending || cell.outcome === null
  }
  // Stable: two groups of one rank keep the order the plan gave them.
  const ordered = [...groups.values()].sort((a, b) => a.rank - b.rank)
  const seen = new Set(leaveOut)
  for (const view of ordered) {
    for (const cell of view.cells) {
      for (const hit of cell.hits) {
        if (seen.has(hit.key)) continue
        seen.add(hit.key)
        view.hits.push(hit)
      }
    }
  }
  return ordered
}

/** Every hit of the answer, once. */
export function hitsOf(state: AnswerState): Hit[] {
  return groupsOf(state).flatMap((group) => group.hits)
}

/** The cells still being asked. */
export function pendingOf(state: AnswerState): CellState[] {
  return state.cells.filter((cell) => cell.outcome === null)
}

/** The cells that did not answer in the time they were given. */
export function lateOf(state: AnswerState): CellState[] {
  return state.cells.filter((cell) => cell.outcome?.status === "late")
}

/**
 * Whether to say "Nothing found": only when the end line says every cell asked
 * was complete (D201), and nothing has been found since by a follow-up.
 */
export function nothingFound(state: AnswerState): boolean {
  return state.end?.nothing_found === true && hitsOf(state).length === 0 && pendingOf(state).length === 0
}

function isSavedQueryText(hit: Hit): boolean {
  return (
    hit.target.kind === "object" &&
    hit.target.object_type === "saved_query" &&
    (hit.match.field === "contents" || hit.match.field === "body")
  )
}

/**
 * Whether this answer found the text of a saved query (D204). Such words are
 * not kept among the recent searches (D205), whatever field the provider
 * reports the match in.
 *
 * Read from every cell's own hits, not from the groups: a query found by its
 * title as well is drawn once, as the title's hit, and its text would be
 * missed.
 */
export function foundSavedQueryText(state: AnswerState): boolean {
  return state.cells.some((cell) => cell.hits.some(isSavedQueryText))
}
