import { describe, expect, it } from "vitest"

import { makeLeaf, makeSplit } from "./model"
import { isSectionHidden } from "./visibility"

/** The feature has an empty view for "work" and none for "navigate". */
const hasEmptyView = (accepts: string | null) => accepts === "work"

const work = (id: string, panels: string[]) =>
  makeLeaf(id, panels, { accepts: "work", pinned: panels.length === 0 })

describe("whether a section is on screen at all", () => {
  it("shows one that holds something", () => {
    const tree = work("work", ["rows:1"])
    expect(isSectionHidden(tree, tree, hasEmptyView)).toBe(false)
  })

  it("hides an empty column the feature has nothing to say about", () => {
    const tree = makeLeaf("navigate", [], { accepts: "navigate", pinned: true })
    expect(isSectionHidden(tree, tree, hasEmptyView)).toBe(true)
  })

  it("shows an empty column while nothing else does its job", () => {
    const tree = makeSplit("root", "row", [makeLeaf("sources", ["connectors"]), work("work", [])], [30, 70])
    const empty = tree.children[1]
    if (empty === undefined) throw new Error("no section")
    expect(isSectionHidden(tree, empty, hasEmptyView)).toBe(false)
  })

  it("hides it once another section of its role holds something", () => {
    // Otherwise the screen says "pick a table to read it here" beside a table
    // that is open: a section split off inherits the role, so a pinned column
    // can be left empty while its role is served two inches away.
    const tree = makeSplit("root", "column", [work("work", []), work("torn", ["rows:1"])], [50, 50])
    const empty = tree.children[0]
    if (empty === undefined) throw new Error("no section")
    expect(isSectionHidden(tree, empty, hasEmptyView)).toBe(true)
  })

  it("shows it again when that section is empty too", () => {
    const tree = makeSplit("root", "column", [work("work", []), work("other", [])], [50, 50])
    const empty = tree.children[0]
    if (empty === undefined) throw new Error("no section")
    expect(isSectionHidden(tree, empty, hasEmptyView)).toBe(false)
  })

  // A section on the bar at the foot of the screen is not on the screen, so
  // the rules above read it as holding nothing: the column of work comes back
  // as what it says can be opened in it, and a column with nothing to say
  // gives its room to the ones that are left.
  it("stands in for a column of work that was put aside", () => {
    const aside = { ...work("work", ["rows:1"]), minimized: true }
    const tree = makeSplit("root", "row", [makeLeaf("sources", ["connectors"]), aside], [30, 70])
    expect(isSectionHidden(tree, aside, hasEmptyView)).toBe(false)
  })

  it("hides a column that was put aside and has nothing to stand in for it", () => {
    const aside = { ...makeLeaf("navigate", ["catalog:1"], { accepts: "navigate" }), minimized: true }
    const tree = makeSplit("root", "row", [makeLeaf("sources", ["connectors"]), aside], [30, 70])
    expect(isSectionHidden(tree, aside, hasEmptyView)).toBe(true)
  })

  it("does not count a section put aside as doing its role on the screen", () => {
    // Otherwise the empty column beside it would stay hidden and the screen
    // would be one column wide with everything else on the bar.
    const tree = makeSplit(
      "root",
      "column",
      [work("work", []), { ...work("torn", ["rows:1"]), minimized: true }],
      [50, 50]
    )
    const empty = tree.children[0]
    if (empty === undefined) throw new Error("no section")
    expect(isSectionHidden(tree, empty, hasEmptyView)).toBe(false)
  })

  it("hides a split whose every section is hidden", () => {
    const inner = makeSplit(
      "inner",
      "column",
      [makeLeaf("a", [], { accepts: "navigate", pinned: true }), makeLeaf("b", [], { accepts: "navigate", pinned: true })],
      [50, 50]
    )
    const tree = makeSplit("root", "row", [makeLeaf("sources", ["connectors"]), inner], [30, 70])
    expect(isSectionHidden(tree, inner, hasEmptyView)).toBe(true)
  })

  it("keeps a split in which one section is still on screen", () => {
    const inner = makeSplit(
      "inner",
      "column",
      [makeLeaf("a", [], { accepts: "navigate", pinned: true }), makeLeaf("b", ["catalog:1"], { accepts: "navigate" })],
      [50, 50]
    )
    const tree = makeSplit("root", "row", [makeLeaf("sources", ["connectors"]), inner], [30, 70])
    expect(isSectionHidden(tree, inner, hasEmptyView)).toBe(false)
  })
})
