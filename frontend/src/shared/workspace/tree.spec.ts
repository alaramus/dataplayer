import { describe, expect, it } from "vitest"

import { makeLeaf, makeSplit } from "./model"
import { leavesOf, nodeAt, pathOfNode, pathOfPanel } from "./tree"

const sample = () =>
  makeSplit("root", "row", [makeLeaf("a", ["p1"]), makeLeaf("b", ["p2", "p3"])], [30, 70])

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
