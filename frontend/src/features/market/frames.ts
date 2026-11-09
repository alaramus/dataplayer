/**
 * What a watch's socket says (D323).
 *
 * Written out again from `app/connectors/watch.py`, for the reason the
 * application's socket gives: OpenAPI has no WebSocket channel, so
 * `src/client` cannot carry these.
 */

export type WatchRefusal =
  | "unauthenticated"
  | "malformed"
  | "not_found"
  | "forbidden"
  | "disabled"
  | "unsupported"
  | "source"

export type LiveMode = "replace" | "append" | "upsert"

/** Rows of one part of what is watched, in the columns the grid shows. */
export interface LiveRows {
  part: string
  mode: LiveMode
  columns: string[]
  rows: (string | null)[][]
  key: string[]
}

export type WatchServerFrame =
  | { type: "ready"; intervals: string[]; interval: string | null }
  | ({ type: "rows" } & LiveRows)
  | { type: "refused"; code: WatchRefusal; message: string; error_kind: string | null }
  | { type: "ended"; message: string; error_kind: string | null }

export function openingFrame(
  token: string,
  connectorId: string,
  nodeId: string,
  interval: string | null
): string {
  return JSON.stringify({
    type: "open",
    token,
    connector_id: connectorId,
    node_id: nodeId,
    interval,
  })
}

function strings(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((one) => typeof one === "string") ? value : null
}

function rowsOf(value: unknown): (string | null)[][] | null {
  if (!Array.isArray(value)) return null
  for (const row of value) {
    if (!Array.isArray(row) || !row.every((cell) => cell === null || typeof cell === "string")) {
      return null
    }
  }
  return value as (string | null)[][]
}

const MODES: readonly LiveMode[] = ["replace", "append", "upsert"]

/**
 * A frame from the server, or null when it is not one this client knows.
 *
 * Checked field by field rather than cast, as a terminal's are: a frame from a
 * newer server read as something it is not would draw a wrong price.
 */
export function readServerFrame(text: string): WatchServerFrame | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof parsed !== "object" || parsed === null) return null
  const frame = parsed as Record<string, unknown>
  switch (frame.type) {
    case "ready": {
      const intervals = strings(frame.intervals)
      if (intervals === null) return null
      return {
        type: "ready",
        intervals,
        interval: typeof frame.interval === "string" ? frame.interval : null,
      }
    }
    case "rows": {
      const columns = strings(frame.columns)
      const rows = rowsOf(frame.rows)
      const mode = MODES.find((one) => one === frame.mode)
      if (typeof frame.part !== "string" || columns === null || rows === null || mode === undefined) {
        return null
      }
      return { type: "rows", part: frame.part, mode, columns, rows, key: strings(frame.key) ?? [] }
    }
    case "refused":
    case "ended":
      if (typeof frame.message !== "string") return null
      if (frame.type === "refused") {
        if (typeof frame.code !== "string") return null
        return {
          type: "refused",
          code: frame.code as WatchRefusal,
          message: frame.message,
          error_kind: typeof frame.error_kind === "string" ? frame.error_kind : null,
        }
      }
      return {
        type: "ended",
        message: frame.message,
        error_kind: typeof frame.error_kind === "string" ? frame.error_kind : null,
      }
    default:
      return null
  }
}
