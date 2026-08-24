import { beforeEach, describe, expect, it, vi } from "vitest"

import { createRealtimeSocket } from "@/shared/realtime/socket"
import type { SocketLike } from "@/shared/realtime/socket"

/**
 * A WebSocket that never leaves the test.
 *
 * The client is ours rather than a library because the part that matters —
 * authenticate on open, then restate every subscription — is ours either way.
 * Being ours, it can be driven frame by frame from here, with no server and no
 * waiting on the clock.
 */
class FakeSocket implements SocketLike {
  static opened: FakeSocket[] = []

  sent: string[] = []
  closed = false
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(readonly url: string) {
    FakeSocket.opened.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.closed = true
    this.onclose?.(new CloseEvent("close"))
  }

  open() {
    this.onopen?.(new Event("open"))
  }

  /** What the server would do: accept the token and say it is ready. */
  becomeReady() {
    this.open()
    this.receive({ type: "ready", protocol: 1 })
  }

  deliver(topic: string, payload: unknown) {
    this.receive({ type: "event", topic, payload })
  }

  private receive(frame: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(frame) }))
  }

  /** A drop from the far end, which the client did not ask for. */
  drop() {
    this.onclose?.(new CloseEvent("close"))
  }

  frames(): Record<string, unknown>[] {
    return this.sent.map((raw) => JSON.parse(raw) as Record<string, unknown>)
  }
}

function makeSocket(token: string | null = "a-token") {
  return createRealtimeSocket({
    url: "ws://test/ws",
    token: () => token,
    open: (url) => new FakeSocket(url),
    // No clock in the test: a reconnect happens when the test says so.
    wait: () => Promise.resolve(),
  })
}

function latest(): FakeSocket {
  const socket = FakeSocket.opened.at(-1)
  if (!socket) throw new Error("no socket was opened")
  return socket
}

beforeEach(() => {
  FakeSocket.opened = []
})

describe("the realtime socket", () => {
  it("says who it is before anything else", () => {
    const client = makeSocket()

    client.subscribe("connector.health", () => {})
    latest().open()

    expect(latest().frames()).toEqual([{ type: "auth", token: "a-token" }])
  })

  it("does not open at all without a token", () => {
    const client = makeSocket(null)

    client.subscribe("connector.health", () => {})

    expect(FakeSocket.opened).toHaveLength(0)
  })

  it("asks for its topics only once the server is ready", () => {
    const client = makeSocket()
    client.subscribe("connector.health", () => {})
    const socket = latest()

    socket.becomeReady()

    expect(socket.frames()).toEqual([
      { type: "auth", token: "a-token" },
      { type: "subscribe", topic: "connector.health" },
    ])
  })

  it("hands an event to whoever is watching that topic", () => {
    const heard = vi.fn()
    const client = makeSocket()
    client.subscribe("connector.health", heard)
    latest().becomeReady()

    latest().deliver("connector.health", { connector_id: "abc" })

    expect(heard).toHaveBeenCalledWith({ connector_id: "abc" })
  })

  it("ignores an event for a topic nobody is watching", () => {
    const heard = vi.fn()
    const client = makeSocket()
    client.subscribe("connector.health", heard)
    latest().becomeReady()

    latest().deliver("something.else", {})

    expect(heard).not.toHaveBeenCalled()
  })

  it("opens again after being dropped, and restates what it was watching", async () => {
    const client = makeSocket()
    client.subscribe("connector.health", () => {})
    latest().becomeReady()
    const first = latest()

    first.drop()
    await Promise.resolve()
    await Promise.resolve()
    latest().becomeReady()

    expect(FakeSocket.opened).toHaveLength(2)
    expect(latest()).not.toBe(first)
    expect(latest().frames()).toEqual([
      { type: "auth", token: "a-token" },
      { type: "subscribe", topic: "connector.health" },
    ])
  })

  it("closes when the last watcher goes away", () => {
    const client = makeSocket()
    const stop = client.subscribe("connector.health", () => {})
    latest().becomeReady()

    stop()

    expect(latest().closed).toBe(true)
  })

  it("does not reopen after the last watcher has gone", async () => {
    const client = makeSocket()
    const stop = client.subscribe("connector.health", () => {})
    latest().becomeReady()

    stop()
    await Promise.resolve()
    await Promise.resolve()

    expect(FakeSocket.opened).toHaveLength(1)
  })

  it("keeps the socket while another watcher remains on the topic", () => {
    const client = makeSocket()
    const stop = client.subscribe("connector.health", () => {})
    client.subscribe("connector.health", () => {})
    latest().becomeReady()

    stop()

    expect(latest().closed).toBe(false)
    expect(latest().frames()).not.toContainEqual({
      type: "unsubscribe",
      topic: "connector.health",
    })
  })
})
