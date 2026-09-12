import { describe, expect, it } from "vitest"

import type { LeafNode, SplitNode } from "./model"
import { makeLeaf, makeSplit } from "./model"
import { leavesOf, nodeAt, normalize, pathOfNode, pathOfPanel, renamePanel, replaceAt } from "./tree"
import {
  activatePanel,
  addPanel,
  movePanel,
  removePanel,
  resizeSplit,
  setCollapsed,
  setMinimized,
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

describe("renaming a panel identity", () => {
  it("keeps the tab in place and active", () => {
    const renamed = renamePanel(activatePanel(sample(), "p3"), "p3", "p4") as SplitNode

    expect(renamed.children[1]).toMatchObject({
      panels: ["p2", "p4"],
      activePanel: "p4",
    })
    expect(pathOfPanel(renamed, "p4")).toEqual([1])
    expect(pathOfPanel(renamed, "p3")).toBeNull()
  })
})

describe("a leaf", () => {
  it("makes its first panel the active one by default", () => {
    expect(makeLeaf("a", ["p1", "p2"]).activePanel).toBe("p1")
  })

  it("refuses to be built with no panels at all", () => {
    expect(() => makeLeaf("a", [])).toThrow()
  })

  // A pinned section is the one exception: it is a column that exists whether
  // or not anything has been opened in it yet. See the spec, T2.
  it("is built empty when it is pinned, with nothing active", () => {
    const leaf = makeLeaf("a", [], { pinned: true })
    expect(leaf.panels).toEqual([])
    expect(leaf.activePanel).toBeNull()
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

  it("keeps an empty leaf that is pinned, and clears what it says is active", () => {
    const pinned: LeafNode = { ...emptyLeaf("a"), pinned: true, activePanel: "gone" }
    expect(normalize(pinned)).toEqual({ ...pinned, activePanel: null })
  })

  it("keeps a split whose other children are empty pinned sections", () => {
    const tree = makeSplit(
      "root",
      "row",
      [
        { ...emptyLeaf("a"), pinned: true, activePanel: null },
        makeLeaf("b", ["p2"]),
        { ...emptyLeaf("c"), pinned: true, activePanel: null },
      ],
      [20, 30, 50]
    )
    const next = normalize(tree) as SplitNode
    expect(next.children.map((child) => child.id)).toEqual(["a", "b", "c"])
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

  it("empties a pinned leaf rather than removing it", () => {
    const tree = makeSplit(
      "root",
      "row",
      [makeLeaf("a", ["p1"], { pinned: true }), makeLeaf("b", ["p2"])],
      [30, 70]
    )
    const next = removePanel(tree, "p1") as SplitNode
    const kept = next.children[0] as LeafNode
    expect(kept.id).toBe("a")
    expect(kept.panels).toEqual([])
    expect(kept.activePanel).toBeNull()
  })

  it("puts a panel back into an emptied pinned leaf and activates it", () => {
    const emptied = makeLeaf("a", [], { pinned: true })
    const next = addPanel(makeSplit("root", "row", [emptied, makeLeaf("b", ["p2"])], [30, 70]), "a", "p9") as SplitNode
    const filled = next.children[0] as LeafNode
    expect(filled.panels).toEqual(["p9"])
    expect(filled.activePanel).toBe("p9")
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

describe("putting a section aside", () => {
  it("marks the leaf, keeps what is in it and touches no size", () => {
    const next = setMinimized(sample(), "a", true) as SplitNode
    const put = next.children[0] as LeafNode

    expect(put.minimized).toBe(true)
    expect(put.panels).toEqual(["p1"])
    expect(put.activePanel).toBe("p1")
    expect(next.sizes).toEqual([30, 70])
  })

  it("brings it back when something is opened into it", () => {
    // Otherwise opening a table into a column that is on the bar would do
    // nothing anybody could see.
    const aside = setMinimized(sample(), "a", true)
    const next = addPanel(aside, "a", "p9") as SplitNode
    const back = next.children[0] as LeafNode

    expect(back.minimized).toBe(false)
    expect(back.activePanel).toBe("p9")
  })

  it("brings it back when one of the tabs already in it is asked for", () => {
    // The bug: pressing a connection whose catalog was already open in a
    // column that is on the bar marked the tab active inside a column nobody
    // could see, so the press did nothing at all.
    const aside = setMinimized(sample(), "a", true)
    const next = activatePanel(aside, "p1") as SplitNode
    const back = next.children[0] as LeafNode

    expect(back.minimized).toBe(false)
    expect(back.activePanel).toBe("p1")
  })

  it("brings it back when a tab is dropped beside what is in it", () => {
    const aside = setMinimized(sample(), "a", true)
    const next = splitLeaf(aside, "a", "p2", "bottom", "new") as SplitNode
    const split = next.children[0] as SplitNode
    const stayed = split.children[0] as LeafNode

    expect(stayed.minimized).toBe(false)
  })

  it("leaves a section that was never put aside exactly as it was", () => {
    // A field on every leaf would change every stored tree and every
    // comparison of one.
    const next = addPanel(sample(), "a", "p9") as SplitNode

    expect(next.children[0]).not.toHaveProperty("minimized")
  })
})

describe("resizing", () => {
  it("moves what one side loses to the other", () => {
    const next = resizeSplit(sample(), "root", 0, 1, 10, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(40)
    expect(next.sizes[1]).toBeCloseTo(60)
  })

  it("stops at the minimum instead of crossing it", () => {
    const next = resizeSplit(sample(), "root", 0, 1, -100, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
    expect(next.sizes[1]).toBeCloseTo(90)
  })

  it("refuses to move a border that is already at the minimum", () => {
    const tight = makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"])], [10, 90])
    const next = resizeSplit(tight, "root", 0, 1, -5, 10) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(10)
  })

  it("leaves alone a section standing between the two being moved", () => {
    // The border a user drags is between the two sections they can see, and
    // with a column off the screen those two are not neighbours in the tree.
    // Spending the hidden column's width here would lose the one it will come
    // back at. See P4.
    const columns = makeSplit(
      "root",
      "row",
      [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2"]), makeLeaf("c", ["p3"])],
      [20, 28, 52]
    )
    const next = resizeSplit(columns, "root", 0, 2, 10, 5) as SplitNode
    expect(next.sizes[0]).toBeCloseTo(30)
    expect(next.sizes[1]).toBeCloseTo(28)
    expect(next.sizes[2]).toBeCloseTo(42)
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

describe("the section a split leaves behind", () => {
  const split = (zone: "left" | "bottom" = "left") =>
    splitLeaf(
      makeLeaf("a", ["p1", "p2"], { accepts: "work", pinned: true }),
      "a",
      "p9",
      zone,
      "new"
    ) as SplitNode

  it("takes the role of the section it came from", () => {
    // Without it the first split makes a section with no role, and a role is
    // now what a drop is judged by: nothing could ever be brought into it
    // again, including the panel that made it. See P2.
    expect((split().children[0] as LeafNode).accepts).toBe("work")
  })

  it("takes it whichever side of the split it lands on", () => {
    expect((split("bottom").children[1] as LeafNode).accepts).toBe("work")
  })

  it("does not take the right to stay on screen with nothing in it", () => {
    // Staying empty is a property of a column of the screen, not of every
    // section: an inherited pin would leave a trace behind every split.
    expect((split().children[0] as LeafNode).pinned).toBeUndefined()
  })
})
