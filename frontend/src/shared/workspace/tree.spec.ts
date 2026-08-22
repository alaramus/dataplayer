import { describe, expect, it } from "vitest"

import type { LeafNode, SplitNode } from "./model"
import { makeLeaf, makeSplit } from "./model"
import { leavesOf, nodeAt, normalize, pathOfNode, pathOfPanel, replaceAt } from "./tree"
import {
  activatePanel,
  addPanel,
  movePanel,
  removePanel,
  resizeSplit,
  setCollapsed,
  splitLeaf,
} from "./tree"

const sample = () =>
  makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2", "p3"])], [30, 70])

/** A leaf with no panels: not something makeLeaf builds, but what normalize repairs. */
const emptyLeaf = (id: string): LeafNode => ({
  kind: "leaf",
  id,
  panels: [],
  activePanel: "",
  collapsed: false,
})

describe("addressing a node", () => {
  it("finds the root by the empty path", () => {
    const tree = sample()
    expect(nodeAt(tree, [])).toBe(tree)
  })

  it("finds a child by its index", () => {
    expect(nodeAt(sample(), [1])?.id).toBe("b")
  })

  it("answers null for a path that leads nowhere", () => {
    expect(nodeAt(sample(), [5])).toBeNull()
  })

  it("finds the path of a node by its id", () => {
    expect(pathOfNode(sample(), "b")).toEqual([1])
  })

  it("finds the path of the leaf holding a panel", () => {
    expect(pathOfPanel(sample(), "p3")).toEqual([1])
  })

  it("answers null for a panel nobody holds", () => {
    expect(pathOfPanel(sample(), "nope")).toBeNull()
  })

  it("lists every leaf in order", () => {
    expect(leavesOf(sample()).map((leaf) => leaf.id)).toEqual(["a", "b"])
  })
})

describe("a leaf", () => {
  it("makes its first panel the active one by default", () => {
    expect(makeLeaf("a", ["p1", "p2"]).activePanel).toBe("p1")
  })

  it("refuses to be built with no panels at all", () => {
    expect(() => makeLeaf("a", [])).toThrow()
  })
})

describe("replacing a node", () => {
  it("puts a new node in place of the old one and leaves the original alone", () => {
    const tree = sample()
    const next = replaceAt(tree, [0], makeLeaf("z", ["p9"]))
    expect((next as SplitNode).children[0]!.id).toBe("z")
    expect((tree as SplitNode).children[0]!.id).toBe("a")
  })

  it("removes the child the path names, not whichever one is easiest", () => {
    const next = replaceAt(sample(), [0], null) as SplitNode
    expect(next.children).toHaveLength(1)
    // Asserting the length alone would pass against removing the wrong index.
    expect(next.children[0]?.id).toBe("b")
    expect(next.sizes).toEqual([70])
  })

  it("answers null when the whole tree is removed", () => {
    expect(replaceAt(makeLeaf("a", ["p1"]), [], null)).toBeNull()
  })
})

describe("normalising a tree", () => {
  it("brings the sizes of a split back to a hundred", () => {
    const odd = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [10, 30])
    const sizes = (normalize(odd) as SplitNode).sizes
    expect(sizes[0]).toBeCloseTo(25)
    expect(sizes[1]).toBeCloseTo(75)
  })

  it("replaces a split holding one child with that child", () => {
    const lonely = makeSplit("root", "row", [makeLeaf("a", ["p1"])], [100])
    expect(normalize(lonely)?.id).toBe("a")
  })

  it("drops a leaf that holds no panels", () => {
    const empty = makeSplit("root", "row", [emptyLeaf("a"), makeLeaf("b", ["p2"])], [50, 50])
    expect(normalize(empty)?.id).toBe("b")
  })

  it("flattens a nested split of the same direction into its parent", () => {
    const nested = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit("inner", "row", [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])], [50, 50]),
      ],
      [50, 50]
    )
    const flat = normalize(nested) as SplitNode
    expect(flat.children.map((child) => child.id)).toEqual(["a", "b", "c"])
    expect(flat.sizes.map(Math.round)).toEqual([50, 25, 25])
  })

  it("leaves a nested split of the other direction alone", () => {
    const nested = makeSplit(
      "root",
      "row",
      [
        makeLeaf("a", ["p1"]),
        makeSplit("inner", "column", [makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])], [50, 50]),
      ],
      [50, 50]
    )
    expect((normalize(nested) as SplitNode).children[1]!.kind).toBe("split")
  })

  it("keeps the active panel pointing at a panel the leaf still holds", () => {
    const stale: LeafNode = { kind: "leaf", id: "a", panels: ["p1"], activePanel: "gone", collapsed: false }
    expect((normalize(stale) as LeafNode).activePanel).toBe("p1")
  })

  it("answers null when nothing is left", () => {
    expect(normalize(emptyLeaf("a"))).toBeNull()
  })
})

describe("panels in a leaf", () => {
  it("adds a panel and makes it the active one", () => {
    const next = addPanel(sample(), "a", "p9") as SplitNode
    const leaf = next.children[0] as LeafNode
    expect(leaf.panels).toEqual(["p1", "p9"])
    expect(leaf.activePanel).toBe("p9")
  })

  it("ignores a leaf that is not there", () => {
    const tree = sample()
    expect(addPanel(tree, "nope", "p9")).toBe(tree)
  })

  it("removes a panel and leaves the others", () => {
    const next = removePanel(sample(), "p2") as SplitNode
    expect((next.children[1] as LeafNode).panels).toEqual(["p3"])
  })

  it("removes the leaf along with its last panel", () => {
    expect(removePanel(sample(), "p1")?.id).toBe("b")
  })

  it("activates a panel the leaf already holds", () => {
    const next = activatePanel(sample(), "p3") as SplitNode
    expect((next.children[1] as LeafNode).activePanel).toBe("p3")
  })
})

describe("collapsing a section", () => {
  it("marks the leaf and touches no size", () => {
    const next = setCollapsed(sample(), "a", true) as SplitNode
    expect((next.children[0] as LeafNode).collapsed).toBe(true)
    expect(next.sizes).toEqual([30, 70])
  })
})

describe("resizing", () => {
  it("moves what one side loses to the other", () => {
    const next = resizeSplit(sample(), "root", 0, 10, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(40)
    expect(next.sizes[1]).toBeCloseTo(60)
  })

  it("stops at the minimum instead of crossing it", () => {
    const next = resizeSplit(sample(), "root", 0, -100, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
    expect(next.sizes[1]).toBeCloseTo(90)
  })

  it("refuses to move a border that is already at the minimum", () => {
    const tight = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [10, 90])
    const next = resizeSplit(tight, "root", 0, -5, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
  })
})

describe("splitting a leaf", () => {
  it("puts the panel to the left in a row", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "left", "new") as SplitNode
    expect(next.direction).toBe("row")
    expect((next.children[0] as LeafNode).panels).toEqual(["p9"])
    expect((next.children[1] as LeafNode).panels).toEqual(["p1"])
    expect(next.sizes).toEqual([50, 50])
  })

  it("puts the panel below in a column", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "bottom", "new") as SplitNode
    expect(next.direction).toBe("column")
    expect((next.children[1] as LeafNode).panels).toEqual(["p9"])
  })

  it("adds the panel as a tab when the zone is the centre", () => {
    const next = splitLeaf(makeLeaf("a", ["p1"]), "a", "p9", "center", "new") as LeafNode
    expect(next.kind).toBe("leaf")
    expect(next.panels).toEqual(["p1", "p9"])
  })
})

describe("moving a panel", () => {
  it("takes it out of one leaf and into another as a tab", () => {
    const next = movePanel(sample(), "p1", "b", "center", "new") as LeafNode
    expect(next.kind).toBe("leaf")
    expect(next.panels).toEqual(["p2", "p3", "p1"])
  })

  it("splits the target when the zone is an edge", () => {
    const next = movePanel(sample(), "p2", "a", "right", "new") as SplitNode
    expect(next.children.map((child) => (child as LeafNode).panels)).toEqual([
      ["p1"],
      ["p2"],
      ["p3"],
    ])
  })

  it("does nothing when the target leaf disappeared with the panel", () => {
    const tree = sample()
    expect(movePanel(tree, "p1", "a", "right", "new")).toBe(tree)
  })
})
