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
