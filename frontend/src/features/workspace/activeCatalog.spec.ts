import { describe, expect, it } from "vitest"

import { activeCatalogPanel } from "./activeCatalog"
import { makeLeaf, makeSplit } from "@/shared/workspace"

const twoColumns = () =>
  makeSplit(
    "root",
    "row",
    [
      makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
      makeLeaf("navigate", ["catalog:a", "catalog:b"], {
        accepts: "navigate",
        pinned: true,
        activePanel: "catalog:b",
      }),
    ],
    [30, 70]
  )

const twoCatalogColumns = () =>
  makeSplit(
    "root",
    "row",
    [
      makeLeaf("navigate", ["catalog:a"], { accepts: "navigate", pinned: true }),
      makeLeaf("navigate-2", ["catalog:b"], { accepts: "navigate" }),
    ],
    [50, 50]
  )

describe("the catalog being looked at", () => {
  it("is the active tab of the column that holds catalogs", () => {
    expect(activeCatalogPanel(twoColumns(), null)).toBe("catalog:b")
  })

  it("is the one in the section the user last touched", () => {
    // With several catalogs open, "the first one found" answers with the one
    // opened earliest rather than the one being read. See P7.
    expect(activeCatalogPanel(twoCatalogColumns(), "navigate-2")).toBe("catalog:b")
    expect(activeCatalogPanel(twoCatalogColumns(), "navigate")).toBe("catalog:a")
  })

  it("ignores a section of another role that happens to be focused", () => {
    expect(activeCatalogPanel(twoColumns(), "sources")).toBe("catalog:b")
  })

  it("is nothing while no catalog is open", () => {
    const tree = makeSplit(
      "root",
      "row",
      [
        makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
        makeLeaf("navigate", [], { accepts: "navigate", pinned: true }),
      ],
      [30, 70]
    )
    expect(activeCatalogPanel(tree, "navigate")).toBeNull()
  })

  it("is nothing when no section takes catalogs at all", () => {
    expect(activeCatalogPanel(makeLeaf("work", ["rows:a"], { accepts: "work" }), null)).toBeNull()
  })
})
