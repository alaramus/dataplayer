import { describe, expect, it } from "vitest"

import type { Panel } from "@/features/workspace/panels"
import { makeLeaf, makeSplit } from "@/shared/workspace/model"

import { contextOf, focusedCatalog, MAX_CONTEXT, placeOf } from "./context"

const catalog = (connectorId: string): Panel => ({
  id: `catalog:${connectorId}`,
  kind: "catalog",
  connectorId,
  title: connectorId,
  adapterType: "postgres",
})

const PANELS: Panel[] = [
  catalog("c1"),
  catalog("c2"),
  { id: "search", kind: "search" },
]

const TREE = makeSplit(
  "root",
  "row",
  [
    makeLeaf("navigate", ["catalog:c1", "catalog:c2"], { accepts: "navigate" }),
    makeLeaf("search-leaf", ["search"], { accepts: "navigate" }),
  ],
  [50, 50]
)

describe("the connections a search is told the person is working with", () => {
  it("puts the one being looked at first, once", () => {
    expect(contextOf("c2", ["c1", "c2", "c3"])).toEqual(["c2", "c1", "c3"])
    expect(contextOf(null, ["c1", "c2"])).toEqual(["c1", "c2"])
  })

  it("names at most eight", () => {
    const open = Array.from({ length: 12 }, (_, index) => `c${String(index)}`)
    expect(contextOf("c11", open)).toHaveLength(MAX_CONTEXT)
    expect(contextOf("c11", open)[0]).toBe("c11")
  })
})

describe("the catalog a scope is offered for", () => {
  it("is the catalog shown in the section last pressed", () => {
    expect(focusedCatalog(PANELS, TREE, "navigate", null)?.connectorId).toBe("c1")
  })

  it("is none when the section pressed shows something else", () => {
    expect(focusedCatalog(PANELS, TREE, "search-leaf", null)).toBeNull()
    expect(focusedCatalog(PANELS, TREE, null, null)).toBeNull()
  })

  it("is a floating catalog in front, before any section", () => {
    expect(focusedCatalog(PANELS, TREE, "navigate", "catalog:c2")?.connectorId).toBe("c2")
    expect(focusedCatalog(PANELS, TREE, "navigate", "search")).toBeNull()
  })

  it("asks that connection only, from the level the catalog stood on", () => {
    expect(placeOf({ connectorId: "c1", label: "local pg", nodeId: "public" })).toEqual({
      kind: "connection",
      connector_id: "c1",
      node_id: "public",
    })
  })
})
