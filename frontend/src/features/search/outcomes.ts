import type { Outcome, PlannedCell, SearchRequest } from "@/client"
import { t } from "@/shared/i18n"

import type { CellState } from "./answer"

/**
 * What a person reads about a cell, and what they can do about it (D201).
 *
 * Outcomes are words, never codes. Each sentence has at most one gesture, and
 * a gesture is either another ask — of that cell alone, or of the cells not
 * asked — or a way to somewhere the answer cannot go itself. A label is a
 * getter, so it is read in the language shown when it is drawn.
 */
export type Gesture =
  /** Ask the cell again: it was late, or failed. */
  | { kind: "retry"; label: string }
  /** Ask a connection the health monitor last saw down, all the same. */
  | { kind: "anyway"; label: string }
  /** Search everything: the field asks only what is cheap and near. */
  | { kind: "enter"; label: string }
  /** It stopped at a ceiling: ask it alone, with the whole of D76's. */
  | { kind: "alone"; label: string }
  /** It found more than a group shows. */
  | { kind: "more"; label: string }
  /** Ask every cell that was left out by the ceiling of connections. */
  | { kind: "these"; label: string }
  /** A key whose passphrase is not held, and the person owns it (D147). */
  | { kind: "unlock"; label: string }

export interface Said {
  sentence: string
  gesture: Gesture | null
}

export const RETRY: Gesture = { kind: "retry", get label() { return t("search.gestures.retry") } }
const ANYWAY: Gesture = { kind: "anyway", get label() { return t("search.gestures.anyway") } }
const ENTER: Gesture = { kind: "enter", get label() { return t("search.gestures.enter") } }
const ALONE: Gesture = { kind: "alone", get label() { return t("search.gestures.alone") } }
const MORE: Gesture = { kind: "more", get label() { return t("search.gestures.more") } }
const THESE: Gesture = { kind: "these", get label() { return t("search.gestures.these") } }
const UNLOCK: Gesture = { kind: "unlock", get label() { return t("search.gestures.unlock") } }

/** "2 s", "0.4 s": the deadline a cell was given, as it was set. */
export function secondsOf(seconds: number): string {
  return t("search.outcomes.seconds", { n: String(Number(seconds.toFixed(1))) })
}

/** "14:02", in the reader's own time. */
export function clockOf(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return iso
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`
}

function inConnection(cell: PlannedCell): boolean {
  return cell.cell.place.kind === "connection"
}

/**
 * What one finished cell says, or nothing when there is nothing to say: a
 * complete cell that found all there was is its hits and no sentence.
 */
export function saidOf(outcome: Outcome, cell: PlannedCell): Said | null {
  switch (outcome.status) {
    case "complete":
      if (!outcome.more) return null
      return {
        sentence: t("search.outcomes.found_more"),
        gesture: inConnection(cell) ? MORE : null,
      }
    case "stopped":
      return {
        sentence: outcome.notice ?? t("search.outcomes.stopped"),
        gesture: inConnection(cell) ? ALONE : null,
      }
    case "late":
      return {
        sentence:
          outcome.deadline_seconds === null
            ? t("search.outcomes.late")
            : t("search.outcomes.late_in", { seconds: secondsOf(outcome.deadline_seconds) }),
        gesture: RETRY,
      }
    case "failed":
      if (outcome.error_kind === "locked") {
        return outcome.owned
          ? { sentence: t("search.outcomes.locked"), gesture: UNLOCK }
          : { sentence: t("search.outcomes.locked_by_owner"), gesture: null }
      }
      return { sentence: outcome.message ?? t("search.outcomes.failed"), gesture: RETRY }
    case "skipped":
      switch (outcome.reason) {
        case "switched_off":
          return { sentence: t("search.outcomes.switched_off"), gesture: null }
        case "cannot_search":
          return { sentence: t("search.outcomes.cannot_search"), gesture: null }
        case "unreachable":
          return {
            sentence:
              outcome.since === null
                ? t("search.outcomes.unreachable")
                : t("search.outcomes.unreachable_since", { time: clockOf(outcome.since) }),
            gesture: ANYWAY,
          }
        case "too_costly":
        case "not_in_context":
          return { sentence: t("search.outcomes.not_while_typing"), gesture: ENTER }
        case "not_asked":
          return { sentence: t("search.outcomes.not_searched"), gesture: THESE }
        case null:
          return { sentence: t("search.outcomes.not_searched"), gesture: null }
      }
  }
}

/** "Nothing found in all 12 places", said only when every cell asked was complete. */
export function nothingFoundSentence(asked: number): string {
  return asked === 1
    ? t("search.outcomes.nothing_found_one")
    : t("search.outcomes.nothing_found_all", { n: asked }, asked)
}

/** What the field's status line says while one is still being asked. */
export function stillSearching(pending: number): string {
  return t("search.outcomes.still_searching", { n: pending }, pending)
}

/**
 * The one quiet line the field says about what typing left out: what was
 * late, and what is asked only on Enter.
 */
export function typingNote(cells: readonly CellState[]): string {
  const late = cells.filter((cell) => cell.outcome?.status === "late").length
  const waiting = cells.filter(
    (cell) =>
      cell.outcome?.status === "skipped" &&
      (cell.outcome.reason === "not_in_context" || cell.outcome.reason === "too_costly")
  ).length
  const parts: string[] = []
  if (late > 0) parts.push(t("search.outcomes.typing_late", { n: late }, late))
  if (waiting > 0) parts.push(t("search.outcomes.typing_waiting", { n: waiting }, waiting))
  if (parts.length === 0) return ""
  return t("search.outcomes.typing_enter", { parts: parts.join(" · ") })
}

/** The most a request may name in `only` (the server's MAX_CONTEXT). */
export const MAX_ONLY = 8

/**
 * The ask a gesture makes, or null for one that goes somewhere instead.
 *
 * Always lane `follow`, so it neither ends nor is ended by the search the tab
 * holds or the words in the field (D200).
 */
export function followOf(
  gesture: Gesture,
  words: string,
  cell: PlannedCell,
  all: readonly CellState[]
): SearchRequest | null {
  const base = { words, mode: "search" as const, lane: "follow" as const }
  switch (gesture.kind) {
    // A place that was late or failed is held back from the same person for
    // a while (D200); a press on Try again is that person asking all the same.
    case "retry":
    case "anyway":
      return { ...base, only: [cell.cell.place], insist: true }
    case "alone":
    case "more":
      return { ...base, only: [cell.cell.place] }
    case "these":
      return {
        ...base,
        only: all
          .filter(
            (one) => one.outcome?.status === "skipped" && one.outcome.reason === "not_asked"
          )
          .slice(0, MAX_ONLY)
          .map((one) => one.planned.cell.place),
        insist: true,
      }
    case "enter":
    case "unlock":
      return null
  }
}
