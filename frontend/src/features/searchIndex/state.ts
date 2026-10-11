import type { ContentsScopeState, KeepState, Outcome, PlannedCell } from "@/client"
import { ageLabel } from "@/shared/freshness/freshness"

/**
 * What a kept list of names is said to be (D212). Plain functions, so what a
 * window and the tool at the foot say can be tested without mounting them.
 */

export type KeepWindow = NonNullable<KeepState["window_seconds"]>

export const KEEP_WINDOWS: readonly { value: KeepWindow; label: string }[] = [
  { value: 3600, label: "1 hour" },
  { value: 21600, label: "6 hours" },
  { value: 86400, label: "1 day" },
  { value: 604800, label: "1 week" },
]

export const DEFAULT_WINDOW: KeepWindow = 86400

export function windowName(seconds: number | undefined): string {
  return KEEP_WINDOWS.find((one) => one.value === seconds)?.label ?? "1 day"
}

function count(names: number | undefined): string {
  const many = names ?? 0
  return `${many.toLocaleString("en-US")} ${many === 1 ? "name" : "names"}`
}

function since(moment: string | null | undefined, now: number): string | null {
  if (!moment) return null
  return `${ageLabel(now - Date.parse(moment))} ago`
}

/** One line: what the list holds, how old it is, and what happened last. */
export function statusLine(state: KeepState, now: number = Date.now()): string {
  const read = since(state.kept_at, now)
  const held = read === null ? null : `${count(state.names)}, read ${read}`
  switch (state.status) {
    case "off":
      return "Not kept"
    case "waiting":
      return "Waiting for its first reading"
    case "reading":
      return held === null ? "Reading names…" : `Reading names again… ${held}`
    case "kept":
      return state.stale ? `${held ?? ""} · changed since, reading again soon` : held ?? ""
    case "partial":
      return [held, state.notice].filter(Boolean).join(" · ")
    case "failed":
      return held === null
        ? `Reading failed: ${state.notice ?? "unknown reason"}`
        : `Last reading failed: ${state.notice ?? "unknown reason"}. Still using ${held}`
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
  return nodeId === "" ? "The whole connection" : nodeId
}

/** What is kept of one folder's files, and what the rule left out. */
export function contentsLine(scope: ContentsScopeState, now: number = Date.now()): string {
  if (!scope.read_at) return "Waiting for its first reading"
  const files = scope.files ?? 0
  const parts = [
    `${files.toLocaleString("en-US")} ${files === 1 ? "file" : "files"}, read ${since(scope.read_at, now) ?? ""}`,
  ]
  const unread = scope.unread ?? 0
  if (unread > 0) {
    parts.push(`${unread.toLocaleString("en-US")} not text or too large`)
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
  const folders = `${scopes.length.toLocaleString("en-US")} ${scopes.length === 1 ? "folder" : "folders"}`
  return `${names} · text of ${files.toLocaleString("en-US")} ${files === 1 ? "file" : "files"} in ${folders}`
}
