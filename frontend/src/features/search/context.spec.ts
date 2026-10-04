import { describe, expect, it } from "vitest"

import type { Panel } from "@/features/workspace/panels"
import { makeLeaf, makeSplit } from "@/shared/workspace/model"

import { contextOf, focusedCatalog, hintsOf, MAX_CONTEXT, offeredScope, placeOf } from "./context"

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

describe("the scope the field offers", () => {
  const rows = (connectorId: string, connectorName: string): Panel => ({
    id: `rows:${connectorId}:orders`,
    kind: "rows",
    connectorId,
    nodeId: "orders",
    title: "orders",
    connectorName,
    adapterType: "postgres",
  })

  const withWork = (navigatePanels: string[], workPanels: string[]) =>
    makeSplit(
      "root",
      "row",
      [
        makeLeaf("navigate", navigatePanels, { accepts: "navigate", pinned: true }),
        makeLeaf("work", workPanels, { accepts: "work", pinned: true }),
      ],
      [50, 50]
    )

  const searchFromOf = (panelId: string) => (panelId === "catalog:c1" ? "public" : null)
  const labelOf = (connectorId: string) => (connectorId === "c1" ? "Live name" : null)

  it("is the focused catalog, standing where it stands and under its current name", () => {
    // The catalog's stored title lags a rename; the chip carries the live name.
    const oldCatalog: Panel = {
      id: "catalog:c1",
      kind: "catalog",
      connectorId: "c1",
      title: "Old name",
      adapterType: "postgres",
    }
    const panels: Panel[] = [oldCatalog, rows("c2", "Other")]
    const scope = offeredScope(panels, withWork(["catalog:c1"], ["rows:c2:orders"]), "navigate", null, searchFromOf, labelOf)
    expect(scope).toEqual({ connectorId: "c1", label: "Live name", nodeId: "public" })
  })

  it("survives closing the last table: the emptied work column falls back to the catalog", () => {
    // Closing the table leaves the focus on the work column, now empty, while
    // the catalog is still open beside it.
    const panels: Panel[] = [catalog("c1")]
    const scope = offeredScope(panels, withWork(["catalog:c1"], []), "work", null, searchFromOf, labelOf)
    expect(scope).toEqual({ connectorId: "c1", label: "Live name", nodeId: "public" })
  })

  it("falls back to the catalog when the focus was never set or is on the connections", () => {
    const panels: Panel[] = [catalog("c1")]
    const tree = withWork(["catalog:c1"], [])
    expect(offeredScope(panels, tree, null, null, searchFromOf, labelOf)?.connectorId).toBe("c1")
    const withSources = makeSplit(
      "root",
      "row",
      [
        makeLeaf("sources", ["connectors"], { accepts: "sources", pinned: true }),
        makeLeaf("navigate", ["catalog:c1"], { accepts: "navigate", pinned: true }),
      ],
      [30, 70]
    )
    expect(offeredScope(panels, withSources, "sources", null, searchFromOf, labelOf)?.connectorId).toBe("c1")
  })

  it("prefers the table being looked at over a catalog open behind it", () => {
    const panels: Panel[] = [catalog("c1"), rows("c2", "Other")]
    const scope = offeredScope(panels, withWork(["catalog:c1"], ["rows:c2:orders"]), "work", null, searchFromOf, labelOf)
    expect(scope).toEqual({ connectorId: "c2", label: "Other", nodeId: null })
  })

  it("is the floating tab in front when it names a connection", () => {
    const panels: Panel[] = [catalog("c1"), rows("c2", "Other")]
    const scope = offeredScope(panels, withWork(["catalog:c1"], []), "navigate", "rows:c2:orders", searchFromOf, labelOf)
    expect(scope).toEqual({ connectorId: "c2", label: "Other", nodeId: null })
  })

  it("never mistakes a tab title for a connection name", () => {
    const result: Panel = {
      id: "result:1",
      kind: "result",
      resultId: "r1",
      title: "Yesterday's run",
      connectorId: "c9",
    }
    const panels: Panel[] = [result]
    const tree = makeSplit(
      "root",
      "row",
      [makeLeaf("work", ["result:1"], { accepts: "work", pinned: true })],
      [100]
    )
    expect(offeredScope(panels, tree, "work", null, () => null, () => null)).toBeNull()
  })

  it("is nothing when no open tab names a connection", () => {
    const panels: Panel[] = [{ id: "search", kind: "search" }]
    const tree = makeSplit(
      "root",
      "row",
      [makeLeaf("navigate", ["search"], { accepts: "navigate", pinned: true })],
      [100]
    )
    expect(offeredScope(panels, tree, "navigate", null, () => null, () => null)).toBeNull()
  })
})

describe("the hints a request carries", () => {
  const OPENED = [{ kind: "connection" as const, connector_id: "c1" }]
  const TABS = [{ object_type: "tab" as const, object_id: "p1", title: "orders" }]

  it("carries what was opened and the open tabs", () => {
    expect(hintsOf(OPENED, TABS)).toEqual({ recent: OPENED, browser: TABS })
  })

  it("leaves an empty list out", () => {
    expect(hintsOf([], [])).toEqual({})
    expect(hintsOf([], TABS)).toEqual({ browser: TABS })
  })
})
