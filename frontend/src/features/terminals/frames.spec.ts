import { describe, expect, it } from "vitest"

import { openingFrame, readServerFrame, resizeFrame } from "./frames"

describe("what a terminal's socket says in text", () => {
  it("opens with who is asking, for which connection, at what size", () => {
    expect(JSON.parse(openingFrame("t0k3n", "c1", { cols: 120, rows: 40 }))).toEqual({
      type: "open",
      token: "t0k3n",
      connector_id: "c1",
      cols: 120,
      rows: 40,
    })
  })

  it("says a new size and nothing else", () => {
    expect(JSON.parse(resizeFrame({ cols: 80, rows: 24 }))).toEqual({
      type: "resize",
      cols: 80,
      rows: 24,
    })
  })

  it("reads each frame the server sends", () => {
    expect(readServerFrame('{"type":"ready"}')).toEqual({ type: "ready" })
    expect(
      readServerFrame(
        '{"type":"refused","code":"source","message":"The SSH key is locked","error_kind":"locked"}'
      )
    ).toEqual({
      type: "refused",
      code: "source",
      message: "The SSH key is locked",
      error_kind: "locked",
    })
    expect(readServerFrame('{"type":"ended","exit_status":3}')).toEqual({
      type: "ended",
      exit_status: 3,
    })
    expect(readServerFrame('{"type":"ended","exit_status":null}')).toEqual({
      type: "ended",
      exit_status: null,
    })
  })

  it("reads nothing into a frame it does not know", () => {
    expect(readServerFrame("not json")).toBeNull()
    expect(readServerFrame('{"type":"welcome"}')).toBeNull()
    expect(readServerFrame('{"type":"refused","code":"source"}')).toBeNull()
    expect(readServerFrame("[]")).toBeNull()
  })
})
