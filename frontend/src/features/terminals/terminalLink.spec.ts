import { describe, expect, it } from "vitest"

import { openTerminalLink } from "./terminalLink"
import type { LinkState, TerminalSocketLike } from "./terminalLink"

class FakeSocket implements TerminalSocketLike {
  binaryType: BinaryType = "blob"
  sent: (string | Uint8Array)[] = []
  closedWith: number | undefined | null = null
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView) {
    this.sent.push(typeof data === "string" ? data : new Uint8Array(data as ArrayBuffer))
  }
  close(code?: number) {
    this.closedWith = code
  }
  open() {
    this.onopen?.(new Event("open"))
  }
  text(frame: object) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(frame) }))
  }
  bytes(data: number[]) {
    this.onmessage?.(new MessageEvent("message", { data: new Uint8Array(data).buffer }))
  }
  drop() {
    this.onclose?.(new CloseEvent("close"))
  }
}

function linked() {
  const socket = new FakeSocket()
  const states: LinkState[] = []
  const output: number[][] = []
  const link = openTerminalLink({
    url: "ws://server/api/v1/terminals",
    token: "t0k3n",
    connectorId: "c1",
    size: { cols: 80, rows: 24 },
    onOutput: (data) => output.push([...data]),
    onState: (state) => states.push(state),
    open: () => socket,
  })
  return { socket, states, output, link }
}

describe("a terminal's socket", () => {
  it("asks for output as bytes and opens with the size it has by then", () => {
    const { socket, link } = linked()
    link.resize({ cols: 132, rows: 43 })
    socket.open()

    expect(socket.binaryType).toBe("arraybuffer")
    // The size is carried by the opening frame, not sent before it.
    expect(socket.sent).toHaveLength(1)
    expect(JSON.parse(socket.sent[0] as string)).toMatchObject({
      type: "open",
      connector_id: "c1",
      cols: 132,
      rows: 43,
    })
  })

  it("is open once the server says the shell is ready, and hands output on", () => {
    const { socket, states, output } = linked()
    socket.open()
    socket.text({ type: "ready" })
    socket.bytes([104, 105])

    expect(states).toEqual([{ kind: "open" }])
    expect(output).toEqual([[104, 105]])
  })

  it("sends keystrokes as UTF-8 bytes, and a new size as text", () => {
    const { socket, link } = linked()
    socket.open()
    socket.text({ type: "ready" })
    link.type("ё\r")
    link.resize({ cols: 100, rows: 30 })

    expect([...(socket.sent[1] as Uint8Array)]).toEqual([0xd1, 0x91, 0x0d])
    expect(JSON.parse(socket.sent[2] as string)).toEqual({ type: "resize", cols: 100, rows: 30 })
  })

  it("sends what the terminal could not put as text byte for byte", () => {
    const { socket, link } = linked()
    socket.open()
    link.typeBytes("\x1b[M\xff")

    expect([...(socket.sent[1] as Uint8Array)]).toEqual([0x1b, 0x5b, 0x4d, 0xff])
  })

  it("says why no shell was opened, and a close after that changes nothing", () => {
    const { socket, states } = linked()
    socket.open()
    socket.text({
      type: "refused",
      code: "source",
      message: "The SSH key is locked",
      error_kind: "locked",
    })
    socket.drop()

    expect(states).toEqual([
      { kind: "refused", code: "source", message: "The SSH key is locked", errorKind: "locked" },
    ])
  })

  it("says the shell ended, with its status", () => {
    const { socket, states } = linked()
    socket.open()
    socket.text({ type: "ready" })
    socket.text({ type: "ended", exit_status: 0 })
    socket.drop()

    expect(states.at(-1)).toEqual({ kind: "ended", exitStatus: 0 })
  })

  it("is lost when the socket closes without a word, and never tries again", () => {
    const { socket, states, link } = linked()
    socket.open()
    socket.text({ type: "ready" })
    socket.drop()
    link.type("ls\r")

    expect(states.at(-1)).toEqual({ kind: "lost" })
    expect(socket.sent).toHaveLength(1)
  })

  it("says nothing more once it has been closed from this side", () => {
    const { socket, states, link } = linked()
    socket.open()
    link.close()
    socket.drop()

    expect(socket.closedWith).toBe(1000)
    expect(states).toEqual([])
  })

  it("sends nothing before the socket is open", () => {
    const { socket, link } = linked()
    link.type("too early")

    expect(socket.sent).toEqual([])
  })
})
