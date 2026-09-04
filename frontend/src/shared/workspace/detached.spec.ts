import { describe, expect, it } from "vitest"

import { dockedLayout, returnPanel } from "./detached"
import type { DetachedPanel } from "./detached"
import { makeLeaf, makeSplit } from "./model"
import { leavesOf } from "./tree"

const detached: DetachedPanel = {
  panelId: "orders", leafId: "work", at: 1, accepts: "work", fallbackLeafId: "returned-1",
}

describe("returning a detached panel", () => {
  it("restores its tab position and expands its original section", () => {
    const tree = { ...makeLeaf("work", ["customers", "products"], { accepts: "work" }), collapsed: true }
    expect(returnPanel(tree, detached)).toMatchObject({
      panels: ["customers", "orders", "products"], activePanel: "orders", collapsed: false,
    })
    expect(tree.panels).toEqual(["customers", "products"])
  })

  it("uses the same role when its old section has gone", () => {
    const tree = makeSplit("root", "row", [
      makeLeaf("sources", ["connections"], { accepts: "sources" }),
      makeLeaf("other-work", ["customers"], { accepts: "work" }),
    ], [30, 70])
    expect(leavesOf(returnPanel(tree, detached)).map((leaf) => leaf.panels)).toEqual([
      ["connections"], ["customers", "orders"],
    ])
  })

  it("recreates a section instead of returning into a different role", () => {
    const tree = makeLeaf("sources", ["connections"], { accepts: "sources" })
    const saved = dockedLayout(tree, [detached, { ...detached, panelId: "products", at: 2 }])
    const leaves = leavesOf(saved)
    expect(leaves.map((leaf) => [leaf.accepts, leaf.panels])).toEqual([
      ["sources", ["connections"]], ["work", ["orders", "products"]],
    ])
  })
})
