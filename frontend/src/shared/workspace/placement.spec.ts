import { describe, expect, it } from "vitest"

import { makeLeaf, makeSplit } from "./model"
import { leafForKind } from "./placement"

const kinds: Record<string, string> = { p1: "catalog", p2: "rows", p3: "rows" }
const kindOf = (panelId: string) => kinds[panelId] ?? null

const tree = makeSplit(
  "root",
  "row",
  [makeLeaf("left", ["p1"]), makeLeaf("main", ["p2", "p3"])],
  [30, 70]
)

describe("where a new panel goes", () => {
  it("joins the section already holding a panel of its kind", () => {
    expect(leafForKind(tree, kindOf, "rows", null)).toBe("main")
  })

  it("falls back to the focused section when no section holds that kind", () => {
    expect(leafForKind(tree, kindOf, "editor", "left")).toBe("left")
  })

  it("falls back to the largest section when nothing has focus", () => {
    expect(leafForKind(tree, kindOf, "editor", null)).toBe("main")
  })

  it("ignores a focused section that is no longer there", () => {
    expect(leafForKind(tree, kindOf, "editor", "gone")).toBe("main")
  })

  it("answers null for a tree with no sections", () => {
    expect(leafForKind(makeSplit("root", "row", [], []), kindOf, "rows", null)).toBeNull()
  })
})

/**
 * A column is a role before it holds anything, which is the part the rules
 * above cannot express: an empty section holds no panel to be read. See the
 * spec, T1.
 */
describe("a section that declares what it accepts", () => {
  const columns = makeSplit(
    "root",
    "row",
    [
      makeLeaf("sources", ["p1"], { accepts: "catalog", pinned: true }),
      makeLeaf("work", [], { accepts: "rows", pinned: true }),
    ],
    [30, 70]
  )

  it("takes the panel even while it is empty", () => {
    expect(leafForKind(columns, kindOf, "rows", null)).toBe("work")
  })

  it("wins over a section that merely happens to hold that kind", () => {
    const mixed = makeSplit(
      "root",
      "row",
      [makeLeaf("stray", ["p2"]), makeLeaf("work", [], { accepts: "rows", pinned: true })],
      [30, 70]
    )
    expect(leafForKind(mixed, kindOf, "rows", null)).toBe("work")
  })

  it("wins over the focused section", () => {
    expect(leafForKind(columns, kindOf, "rows", "sources")).toBe("work")
  })

  it("leaves the earlier rules alone for a kind nothing accepts", () => {
    expect(leafForKind(columns, kindOf, "editor", "sources")).toBe("sources")
  })
})
