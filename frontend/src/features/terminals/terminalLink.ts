import { openingFrame, readServerFrame, resizeFrame } from "./frames"
import type { RefusalCode, TerminalSize } from "./frames"

/**
 * One terminal's socket (D148): it opens, says who is asking, and then carries
 * keystrokes one way and output the other until either side stops.
 *
 * Never reconnects. A new socket is a new shell on the server (D149), so what
 * a reconnect would give back is not the terminal that was lost — the person
 * is told it ended and asks for another. Everything from outside is passed
 * in, so the whole of it is driven from a unit test.
 */

export type LinkState =
  | { kind: "connecting" }
  | { kind: "open" }
  | { kind: "refused"; code: RefusalCode; message: string; errorKind: string | null }
  | { kind: "ended"; exitStatus: number | null }
  /** Closed without a word: the server went away, or the network did. */
  | { kind: "lost" }

/** As much of WebSocket as this file uses, so a test can stand in for it. */
export interface TerminalSocketLike {
  binaryType: BinaryType
  send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void
  close(code?: number): void
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
}

export interface LinkOptions {
  url: string
  token: string
  connectorId: string
  size: TerminalSize
  onOutput: (data: Uint8Array) => void
  onState: (state: LinkState) => void
  open?: (url: string) => TerminalSocketLike
}

export interface TerminalLink {
  /** Keystrokes as the terminal gives them: text, sent as UTF-8. */
  type(data: string): void
  /** Bytes the terminal could not put as text, one character a byte. */
  typeBytes(data: string): void
  resize(size: TerminalSize): void
  close(): void
}

const encoder = new TextEncoder()

export function openTerminalLink(options: LinkOptions): TerminalLink {
  const socket = (options.open ?? ((url: string) => new WebSocket(url)))(options.url)
  socket.binaryType = "arraybuffer"
  let size = options.size
  let state: LinkState = { kind: "connecting" }
  let opened = false
  let closedHere = false

  function become(next: LinkState) {
    state = next
    if (!closedHere) options.onState(next)
  }

  function finished(): boolean {
    return state.kind === "refused" || state.kind === "ended" || state.kind === "lost"
  }

  socket.onopen = () => {
    opened = true
    // The size at this moment rather than the one asked with: the terminal is
    // fitted to its window while the socket is still opening.
    socket.send(openingFrame(options.token, options.connectorId, size))
  }

  socket.onmessage = (event: MessageEvent) => {
    if (event.data instanceof ArrayBuffer) {
      options.onOutput(new Uint8Array(event.data))
      return
    }
    if (typeof event.data !== "string") return
    const frame = readServerFrame(event.data)
    if (frame === null) return
    if (frame.type === "ready") become({ kind: "open" })
    else if (frame.type === "refused")
      become({
        kind: "refused",
        code: frame.code,
        message: frame.message,
        errorKind: frame.error_kind,
      })
    else if (frame.type === "ended") become({ kind: "ended", exitStatus: frame.exit_status })
    // An `error` is the server not understanding one frame of ours; the
    // shell goes on, and there is nothing a person could do about it.
  }

  socket.onclose = () => {
    if (!finished()) become({ kind: "lost" })
  }

  // Keystrokes and sizes go as soon as the socket is open, even before the
  // shell is: the server reads them once it is, in the order they were sent.
  function send(data: string | Uint8Array) {
    if (!opened || finished() || closedHere) return
    socket.send(data)
  }

  return {
    type(data) {
      send(encoder.encode(data))
    },
    typeBytes(data) {
      send(Uint8Array.from(data, (character) => character.charCodeAt(0) & 0xff))
    },
    resize(next) {
      size = next
      send(resizeFrame(next))
    },
    close() {
      closedHere = true
      socket.close(1000)
    },
  }
}
