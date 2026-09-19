/**
 * What a terminal's socket says in text (D148).
 *
 * Written out again from `app/terminals/messages.py`, for the reason the
 * application's socket gives: OpenAPI has no WebSocket channel, so
 * `src/client` cannot carry these. Keystrokes and output are binary frames and
 * are not described here at all.
 */

export type RefusalCode =
  | "unauthenticated"
  | "malformed"
  | "not_found"
  | "forbidden"
  | "disabled"
  | "unsupported"
  | "too_many"
  | "source"

export type TerminalServerFrame =
  | { type: "ready" }
  | { type: "refused"; code: RefusalCode; message: string; error_kind: string | null }
  | { type: "ended"; exit_status: number | null }
  | { type: "error"; message: string }

export interface TerminalSize {
  cols: number
  rows: number
}

export function openingFrame(token: string, connectorId: string, size: TerminalSize): string {
  return JSON.stringify({
    type: "open",
    token,
    connector_id: connectorId,
    cols: size.cols,
    rows: size.rows,
  })
}

export function resizeFrame(size: TerminalSize): string {
  return JSON.stringify({ type: "resize", cols: size.cols, rows: size.rows })
}

/**
 * A text frame from the server, or null when it is not one this client knows.
 *
 * Checked field by field rather than cast: a frame from a newer server read
 * as something it is not would put a wrong sentence on the screen.
 */
export function readServerFrame(text: string): TerminalServerFrame | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof parsed !== "object" || parsed === null) return null
  const frame = parsed as Record<string, unknown>
  switch (frame.type) {
    case "ready":
      return { type: "ready" }
    case "refused":
      if (typeof frame.code !== "string" || typeof frame.message !== "string") return null
      return {
        type: "refused",
        code: frame.code as RefusalCode,
        message: frame.message,
        error_kind: typeof frame.error_kind === "string" ? frame.error_kind : null,
      }
    case "ended":
      return {
        type: "ended",
        exit_status: typeof frame.exit_status === "number" ? frame.exit_status : null,
      }
    case "error":
      return { type: "error", message: typeof frame.message === "string" ? frame.message : "" }
    default:
      return null
  }
}
