import { beforeEach, describe, expect, it } from "vitest"

import {
  clipboard,
  forgetClipboard,
  heldFor,
  holdNodes,
} from "./clipboard"

beforeEach(() => {
  forgetClipboard()
})

describe("what the catalog is holding", () => {
  it("holds nothing until something is copied", () => {
    expect(clipboard.value).toBeNull()
    expect(heldFor("c1")).toBeNull()
  })

  it("remembers what was ticked and which verb was pressed", () => {
    holdNodes("c1", ["reports", "notes.txt"], "move")

    expect(heldFor("c1")).toEqual({
      connectorId: "c1",
      nodeIds: ["reports", "notes.txt"],
      mode: "move",
    })
  })

  it("holds nothing for another connection", () => {
    // An opaque node id means nothing to another source, and the two roots
    // have nothing to do with each other.
    holdNodes("c1", ["notes.txt"], "copy")

    expect(heldFor("c2")).toBeNull()
    expect(heldFor(null)).toBeNull()
  })

  it("does not hold an empty selection", () => {
    holdNodes("c1", [], "copy")

    expect(clipboard.value).toBeNull()
  })

  it("replaces what was held rather than adding to it", () => {
    holdNodes("c1", ["a"], "copy")
    holdNodes("c1", ["b"], "move")

    expect(heldFor("c1")?.nodeIds).toEqual(["b"])
    expect(heldFor("c1")?.mode).toBe("move")
  })

  it("keeps a copy of the selection rather than the array it was given", () => {
    const ticked = ["a"]
    holdNodes("c1", ticked, "copy")
    ticked.push("b")

    expect(heldFor("c1")?.nodeIds).toEqual(["a"])
  })

  it("is forgotten when it lands", () => {
    holdNodes("c1", ["a"], "copy")
    forgetClipboard()

    expect(clipboard.value).toBeNull()
  })
})
