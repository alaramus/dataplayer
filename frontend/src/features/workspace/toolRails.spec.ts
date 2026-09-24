import { describe, expect, it } from "vitest"

import { defaultArrangement, moveBlock, readArrangement } from "./toolRails"
import type { BlockSeat } from "./toolRails"

const BLOCKS: BlockSeat[] = [
  { id: "spaces", home: "left-top" },
  { id: "queries", home: "left-top" },
  { id: "services", home: "left-bottom" },
  { id: "save", home: "right-top" },
  { id: "list", home: "right-top", beside: "save" },
]

describe("the arrangement of the tool rails", () => {
  it("puts every block at home when nothing was stored", () => {
    expect(readArrangement(null, BLOCKS)).toEqual({
      "left-top": ["spaces", "queries"],
      "left-bottom": ["services"],
      "right-top": ["save", "list"],
      "right-bottom": [],
    })
    expect(readArrangement("not json", BLOCKS)).toEqual(defaultArrangement(BLOCKS))
    expect(readArrangement("[1, 2]", BLOCKS)).toEqual(defaultArrangement(BLOCKS))
  })

  it("keeps where somebody put the blocks, without what is no block any more", () => {
    const stored = JSON.stringify({
      "left-top": ["queries", "gone"],
      "left-bottom": [],
      "right-top": ["services", "spaces", "save", "list", "queries"],
      "right-bottom": [],
    })
    expect(readArrangement(stored, BLOCKS)).toEqual({
      "left-top": ["queries"],
      "left-bottom": [],
      "right-top": ["services", "spaces", "save", "list"],
      "right-bottom": [],
    })
  })

  // A block newer than what was stored is not lost, and one that belongs
  // beside another follows it to wherever it was carried.
  it("seats a block the stored arrangement lacks", () => {
    const stored = JSON.stringify({
      "left-top": ["spaces", "queries", "services"],
      "left-bottom": ["save"],
      "right-top": [],
      "right-bottom": [],
    })
    expect(readArrangement(stored, BLOCKS)["left-bottom"]).toEqual(["save", "list"])
    const noSave = JSON.stringify({ "left-top": ["spaces"] })
    const whole = readArrangement(noSave, BLOCKS)
    expect(whole["right-top"]).toEqual(["save", "list"])
    expect(whole["left-bottom"]).toEqual(["services"])
  })

  it("adds a new quick-chat button beside queries in an existing rail layout", () => {
    const previous = JSON.stringify({
      "left-top": ["spaces"],
      "left-bottom": ["queries", "services"],
      "right-top": ["save", "list"],
      "right-bottom": [],
    })
    const withQuickChat: BlockSeat[] = [
      ...BLOCKS,
      { id: "quick-chat", home: "left-top", beside: "queries" },
    ]
    expect(readArrangement(previous, withQuickChat)["left-bottom"]).toEqual([
      "queries", "quick-chat", "services",
    ])
  })

  it("moves a block before the one it is dropped on, across rails or down its own", () => {
    const start = defaultArrangement(BLOCKS)
    const across = moveBlock(start, "list", "left-bottom", "services")
    expect(across["left-bottom"]).toEqual(["list", "services"])
    expect(across["right-top"]).toEqual(["save"])

    const down = moveBlock(start, "spaces", "left-top", null)
    expect(down["left-top"]).toEqual(["queries", "spaces"])
    const three = moveBlock(across, "spaces", "left-bottom", "services")
    expect(three["left-bottom"]).toEqual(["list", "spaces", "services"])
    // Down its own rail: an index into the list it still stood in landed it
    // after "services" instead of before.
    expect(moveBlock(three, "list", "left-bottom", "services")["left-bottom"]).toEqual([
      "spaces", "list", "services",
    ])
    expect(moveBlock(three, "spaces", "left-bottom", "spaces")).toBe(three)
  })
})
