import type { ContentsScopeState, KeepState, Outcome, PlannedCell } from "@/client"
import { ageLabel } from "@/shared/freshness/freshness"
import { t } from "@/shared/i18n"

/**
 * What a kept list of names is said to be (D212). Plain functions, so what a
 * window and the tool at the foot say can be tested without mounting them.
 */

export type KeepWindow = NonNullable<KeepState["window_seconds"]>

// Labels are getters, read in the language shown when they are drawn.
export const KEEP_WINDOWS: readonly { value: KeepWindow; label: string }[] = [
  { value: 3600, get label() { return t("search_index.windows.hour") } },
  { value: 21600, get label() { return t("search_index.windows.six_hours") } },
  { value: 86400, get label() { return t("search_index.windows.day") } },
  { value: 604800, get label() { return t("search_index.windows.week") } },
]

export const DEFAULT_WINDOW: KeepWindow = 86400

export function windowName(seconds: number | undefined): string {
  return KEEP_WINDOWS.find((one) => one.value === seconds)?.label ?? t("search_index.windows.day")
}

function count(names: number | undefined): string {
  const many = names ?? 0
  return t("search_index.state.names", { n: many.toLocaleString("en-US") }, many)
}

function since(moment: string | null | undefined, now: number): string | null {
  if (!moment) return null
  return t("search_index.state.ago", { age: ageLabel(now - Date.parse(moment)) })
}

/** One line: what the list holds, how old it is, and what happened last. */
export function statusLine(state: KeepState, now: number = Date.now()): string {
  const read = since(state.kept_at, now)
  const held = read === null ? null : t("search_index.state.held", { names: count(state.names), ago: read })
  switch (state.status) {
    case "off":
      return t("search_index.state.off")
    case "waiting":
      return t("search_index.state.waiting")
    case "reading":
      return held === null
        ? t("search_index.state.reading")
        : t("search_index.state.reading_again", { held })
    case "kept":
      return state.stale ? t("search_index.state.stale", { held: held ?? "" }) : held ?? ""
    case "partial":
      return [held, state.notice].filter(Boolean).join(" · ")
    case "failed": {
      const reason = state.notice ?? t("search_index.state.unknown_reason")
      return held === null
        ? t("search_index.state.failed", { reason })
        : t("search_index.state.failed_last", { reason, held })
    }
  }
}

/** Whether something is about to change, so the screen asks again soon. */
export function isBusy(state: KeepState): boolean {
  return (
    state.status === "reading" ||
    state.status === "waiting" ||
    state.refresh_asked === true ||
    state.stale === true
  )
}

/** Whether a kept list is what answers the search now. */
export function isKept(state: KeepState): boolean {
  return state.status !== "off"
}

/**
 * Whether a connection's names cell offers "Keep names" beside its own
 * gesture (D212): it was asked live and stopped short or was late, the person
 * owns the connection, its type can keep a list, and it does not keep one yet.
 */
export function offersKeeping(
  planned: PlannedCell,
  outcome: Outcome | null,
  connection: { owned: boolean; adapterType: string } | undefined,
  types: readonly string[],
  kept: ReadonlySet<string>
): boolean {
  const id = planned.connector_id
  return (
    id !== null &&
    id !== undefined &&
    planned.cell.field === "names" &&
    outcome !== null &&
    outcome.way === "live" &&
    (outcome.status === "stopped" || outcome.status === "late") &&
    connection?.owned === true &&
    types.includes(connection.adapterType) &&
    !kept.has(id)
  )
}

/** A folder whose text is kept, by its path; the empty one is everything. */
export function folderName(nodeId: string): string {
  return nodeId === "" ? t("search_index.state.whole_connection") : nodeId
}

/** What is kept of one folder's files, and what the rule left out. */
export function contentsLine(scope: ContentsScopeState, now: number = Date.now()): string {
  if (!scope.read_at) return t("search_index.state.waiting")
  const files = scope.files ?? 0
  const parts = [
    t("search_index.state.files_read", {
      files: t("search_index.state.files", { n: files.toLocaleString("en-US") }, files),
      ago: since(scope.read_at, now) ?? "",
    }),
  ]
  const unread = scope.unread ?? 0
  if (unread > 0) {
    parts.push(t("search_index.state.unread", { n: unread.toLocaleString("en-US") }))
  }
  if (scope.notice) parts.push(scope.notice)
  return parts.join(" · ")
}

/** The tool's one line for a connection: its names, and its folders' text. */
export function summaryLine(state: KeepState, now: number = Date.now()): string {
  const scopes = state.contents ?? []
  const names = statusLine(state, now)
  if (scopes.length === 0) return names
  const files = scopes.reduce((total, scope) => total + (scope.files ?? 0), 0)
  return t("search_index.state.summary", {
    names,
    files: t("search_index.state.summary_files", { n: files.toLocaleString("en-US") }, files),
    folders: t("search_index.state.summary_folders", { n: scopes.length.toLocaleString("en-US") }, scopes.length),
  })
}

/** How much of what is kept the model has read, or that no model runs (D220). */
export function meaningLine(state: KeepState): string {
  const meaning = state.meaning
  if (!meaning) return t("search_index.state.meaning_off")
  const passages = meaning.passages.toLocaleString("en-US")
  const model = meaning.model
  if (meaning.passages === 0) return t("search_index.state.meaning_nothing", { model })
  if (meaning.vectors >= meaning.passages) return t("search_index.state.meaning_all", { n: passages, model })
  return t(
    "search_index.state.meaning_some",
    { vectors: meaning.vectors.toLocaleString("en-US"), n: passages, model },
    meaning.passages
  )
}
