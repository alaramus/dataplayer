import { openingFrame, readServerFrame } from "./frames"
import type { LiveRows, WatchRefusal } from "./frames"

/**
 * One watch's socket (D323): it opens, says what it watches, and then hears
 * rows until it is closed.
 *
 * Unlike a terminal's, a lost watch is opened again: a new socket starts with
 * the node as it stands, so nothing is owed from before the drop. A refusal
 * or an end the server explained is not retried — the same request would be
 * refused again. Everything from outside is passed in, so a unit test drives
 * the whole of it.
 */

export type WatchState =
  | { kind: "connecting" }
  | { kind: "open"; intervals: string[]; interval: string | null }
  | { kind: "refused"; code: WatchRefusal; message: string }
  | { kind: "ended"; message: string }
  /** Closed without a word; opened again after `retryInMs`. */
  | { kind: "lost"; retryInMs: number }

/** As much of WebSocket as this file uses. */
export interface WatchSocketLike {
  send(data: string): void
  close(code?: number): void
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
}

export interface WatchOptions {
  url: string
  token: string
  connectorId: string
  nodeId: string
  interval: string | null
  onRows: (rows: LiveRows) => void
  onState: (state: WatchState) => void
  open?: (url: string) => WatchSocketLike
  /** For a test: how a later attempt is scheduled. */
  later?: (run: () => void, ms: number) => unknown
  cancelLater?: (handle: unknown) => void
}

export interface WatchLink {
  close(): void
}

// Spread a little, so screens that lost the server together do not all come
// back in the same instant.
const RETRY_MS = [1000, 2000, 5000, 10000, 30000]

export function openWatchLink(options: WatchOptions): WatchLink {
  const open = options.open ?? ((url: string) => new WebSocket(url))
  const later = options.later ?? ((run: () => void, ms: number) => setTimeout(run, ms))
  const cancelLater = options.cancelLater ?? ((handle: unknown) => clearTimeout(handle as number))
  let attempt = 0
  let closedHere = false
  let pending: unknown = null
  let socket: WatchSocketLike | null = null

  function connect() {
    pending = null
    let finished = false
    const current = open(options.url)
    socket = current
    options.onState({ kind: "connecting" })
    current.onopen = () => {
      current.send(openingFrame(options.token, options.connectorId, options.nodeId, options.interval))
    }
    current.onmessage = (event: MessageEvent) => {
      if (typeof event.data !== "string" || closedHere) return
      const frame = readServerFrame(event.data)
      if (frame === null) return
      if (frame.type === "ready") {
        attempt = 0
        options.onState({ kind: "open", intervals: frame.intervals, interval: frame.interval })
      } else if (frame.type === "rows") {
        options.onRows(frame)
      } else if (frame.type === "refused") {
        finished = true
        options.onState({ kind: "refused", code: frame.code, message: frame.message })
      } else {
        finished = true
        options.onState({ kind: "ended", message: frame.message })
      }
    }
    current.onclose = () => {
      if (closedHere || finished || socket !== current) return
      const retryInMs = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)] ?? 30000
      attempt += 1
      options.onState({ kind: "lost", retryInMs })
      pending = later(connect, retryInMs)
    }
  }

  connect()
  return {
    close() {
      closedHere = true
      if (pending !== null) cancelLater(pending)
      socket?.close(1000)
    },
  }
}
