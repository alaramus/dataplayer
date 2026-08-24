/**
 * The one socket to the server, and who is listening on it.
 *
 * Written here rather than taken from a library: the part that matters is
 * "on open, say who you are, then restate every subscription", and that is
 * ours whatever opens the connection. What a library would have added is the
 * reconnect delay, which is the short function below.
 *
 * Everything the client needs from the outside — how to open, how to wait, how
 * to find the token — is passed in, so the whole of it can be driven from a
 * unit test with no server and no clock.
 */

/**
 * As much of WebSocket as this file uses, so a test can stand in for it.
 *
 * The handler signatures are the real ones rather than something narrower: a
 * WebSocket has to satisfy this interface without a cast, and a cast is how a
 * test double ends up proving something about a shape nothing else has.
 */
export interface SocketLike {
  send(data: string): void
  close(): void
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
}

/**
 * Frames the server sends.
 *
 * Written by hand rather than generated: OpenAPI has no WebSocket channel, so
 * `src/client` does not carry these. They are checked against the models in
 * `app/realtime/messages.py` by the end-to-end scenarios, which is the only
 * place both sides meet.
 */
export type ServerFrame =
  | { type: "ready"; protocol: number }
  | { type: "event"; topic: string; payload: unknown }
  | { type: "error"; code: string; message: string }

export type Listener = (payload: unknown) => void

export interface SocketOptions {
  url: string
  token: () => string | null
  open?: (url: string) => SocketLike
  wait?: (ms: number) => Promise<void>
}

export interface RealtimeSocket {
  subscribe(topic: string, listener: Listener): () => void
  close(): void
}

const FIRST_DELAY_MS = 500
const LONGEST_DELAY_MS = 15_000

/**
 * How long before trying again, with a spread.
 *
 * The spread matters when a server comes back: without it every tab that lost
 * the connection at the same moment returns at the same moment.
 */
export function reconnectDelay(attempt: number, random = Math.random): number {
  const doubled = FIRST_DELAY_MS * 2 ** Math.min(attempt, 8)
  const capped = Math.min(doubled, LONGEST_DELAY_MS)
  return Math.round(capped * (0.5 + random() * 0.5))
}

export function createRealtimeSocket(options: SocketOptions): RealtimeSocket {
  const openSocket = options.open ?? ((url: string) => new WebSocket(url))
  const wait =
    options.wait ?? ((ms: number) => new Promise((done) => setTimeout(done, ms)))

  const listeners = new Map<string, Set<Listener>>()
  let socket: SocketLike | null = null
  let ready = false
  let attempt = 0
  let wanted = false

  function connect() {
    const token = options.token()
    // Nothing to open with: a socket that cannot authenticate would be closed
    // by the server the moment it opened, and reopened by us in a loop.
    if (token === null) return

    wanted = true
    const opening = openSocket(options.url)
    socket = opening
    ready = false

    opening.onopen = () => {
      opening.send(JSON.stringify({ type: "auth", token }))
    }

    opening.onmessage = (event) => {
      const frame = JSON.parse(String(event.data)) as ServerFrame
      if (frame.type === "ready") {
        ready = true
        attempt = 0
        for (const topic of listeners.keys()) {
          opening.send(JSON.stringify({ type: "subscribe", topic }))
        }
        return
      }
      if (frame.type === "event") {
        for (const listener of listeners.get(frame.topic) ?? []) {
          listener(frame.payload)
        }
      }
    }

    opening.onclose = () => {
      if (socket !== opening) return
      socket = null
      ready = false
      void reopen()
    }
  }

  async function reopen() {
    // Closed on purpose, or nobody left watching: either way, staying shut is
    // the right answer.
    if (!wanted || listeners.size === 0) return
    const delay = reconnectDelay(attempt)
    attempt += 1
    await wait(delay)
    if (!wanted || listeners.size === 0 || socket !== null) return
    connect()
  }

  function subscribe(topic: string, listener: Listener): () => void {
    const first = !listeners.has(topic)
    const forTopic = listeners.get(topic) ?? new Set<Listener>()
    forTopic.add(listener)
    listeners.set(topic, forTopic)

    if (socket === null) connect()
    else if (ready && first) socket.send(JSON.stringify({ type: "subscribe", topic }))

    return () => drop(topic, listener)
  }

  function drop(topic: string, listener: Listener) {
    const forTopic = listeners.get(topic)
    if (!forTopic) return
    forTopic.delete(listener)
    if (forTopic.size > 0) return

    listeners.delete(topic)
    if (ready && socket !== null) {
      socket.send(JSON.stringify({ type: "unsubscribe", topic }))
    }
    // Holding a socket nobody reads keeps a monitor alive on the server, and
    // that monitor opens connections to other people's databases.
    if (listeners.size === 0) close()
  }

  function close() {
    wanted = false
    const closing = socket
    socket = null
    ready = false
    closing?.close()
  }

  return { subscribe, close }
}
