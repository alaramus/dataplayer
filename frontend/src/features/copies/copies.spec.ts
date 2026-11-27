import { describe, expect, it } from "vitest"

import { chosenShown, originLine, sizeLine } from "./copies"

describe("the copy history's lines (D460)", () => {
  it("names where a copy came from, and what in it when that is known", () => {
    expect(originLine({ source: "grid", detail: "email" })).toBe("Grid · email")
    expect(originLine({ source: "agent", detail: null })).toBe("Agent")
  })

  it("speaks of the size only when the list shows less than the copy holds", () => {
    expect(sizeLine({ preview: "short", length: 5, cut: false })).toBeNull()
    expect(sizeLine({ preview: "x".repeat(300), length: 1200, cut: false })).toBe("1,200 characters")
    expect(sizeLine({ preview: "x".repeat(300), length: 65536, cut: true })).toBe(
      "65,536 characters kept, the rest was cut"
    )
  })

  it("deletes only the ticked copies still on the list", () => {
    const chosen = new Set(["a", "gone", "c"])
    expect(chosenShown(chosen, [{ id: "a" }, { id: "b" }, { id: "c" }])).toEqual(["a", "c"])
  })
})
