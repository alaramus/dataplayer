import { describe, expect, it } from "vitest"

import type { Panel } from "@/features/workspace/panels"

import { browserPlacesOf, MAX_BROWSER_PLACES } from "./browser"

const rows = (id: string, title: string): Panel => ({
  id,
  kind: "rows",
  connectorId: "c1",
  nodeId: `public.${title}`,
  title,
  connectorName: "Shop",
  adapterType: "postgres",
})

describe("the places the browser tells the search of", () => {
  it("names each open tab by its title and connection, then each saved group", () => {
    const panels: Panel[] = [
      { id: "connectors", kind: "connectors" },
      { id: "catalog:c1", kind: "catalog", connectorId: "c1", title: "Shop", adapterType: "postgres" },
      rows("rows:orders", "orders"),
      { id: "search", kind: "search" },
    ]
    expect(browserPlacesOf(panels, [{ id: "g1", name: "Morning" }])).toEqual([
      { object_type: "tab", object_id: "catalog:c1", title: "Shop", detail: "Catalog" },
      { object_type: "tab", object_id: "rows:orders", title: "orders", detail: "Shop" },
      { object_type: "tab_group", object_id: "g1", title: "Morning" },
    ])
  })

  it("uses the title on the tab, and the kind where no connection is named", () => {
    const panels: Panel[] = [
      { id: "query:1", kind: "query", title: null, connectorName: null },
    ]
    expect(browserPlacesOf(panels, [])).toEqual([
      { object_type: "tab", object_id: "query:1", title: "Untitled query", detail: "Query" },
    ])
  })

  it("names at most 200, the open tabs first", () => {
    const panels = Array.from({ length: MAX_BROWSER_PLACES + 5 }, (_, at) => rows(`rows:${at}`, `t${at}`))
    const places = browserPlacesOf(panels, [{ id: "g1", name: "Morning" }])
    expect(places).toHaveLength(MAX_BROWSER_PLACES)
    expect(places.every((place) => place.object_type === "tab")).toBe(true)
  })
})
