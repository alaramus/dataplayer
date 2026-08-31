import { describe, expect, it } from "vitest"

import { adapterIcon } from "@/features/connectors/adapters"

import {
  catalogPanelId,
  chartPanelId,
  collapsedOf,
  componentOf,
  contentPanelId,
  emptyOf,
  kindOf,
  lookOf,
  openConnectorIds,
  panelSchema,
  PANEL_ROLES,
  roleOf,
  rowsPanelId,
  structurePanelId,
} from "./panels"
import type { Panel, PanelKind } from "./panels"

const KINDS: PanelKind[] = ["connectors", "catalog", "rows", "content", "structure", "chart"]

const samples: Record<PanelKind, Panel> = {
  connectors: { id: "connectors", kind: "connectors" },
  catalog: {
    id: catalogPanelId("c1"),
    kind: "catalog",
    connectorId: "c1",
    title: "local pg",
    adapterType: "postgres",
  },
  rows: {
    id: rowsPanelId("c1", "public.orders"),
    kind: "rows",
    connectorId: "c1",
    nodeId: "public.orders",
    title: "orders",
    connectorName: "local pg",
    adapterType: "postgres",
    describable: true,
  },
  content: {
    id: contentPanelId("c1", "people.json", "json"),
    kind: "content",
    connectorId: "c1",
    nodeId: "people.json",
    title: "people.json",
    connectorName: "my files",
    adapterType: "file",
    representation: "json",
    tableTitle: "View as table",
  },
  structure: {
    id: structurePanelId("c1", "public.orders"),
    kind: "structure",
    connectorId: "c1",
    nodeId: "public.orders",
    title: "orders",
    connectorName: "local pg",
    adapterType: "postgres",
  },
  chart: {
    id: chartPanelId("view-1"),
    kind: "chart",
    viewKey: "view-1",
    connectorId: "c1",
    title: "orders",
    connectorName: "local pg",
    adapterType: "postgres",
    request: { node_id: "public.orders", limit: 100, offset: 0, filters: [], sort: [] },
    columns: ["created_at", "total"],
  },
}

describe("the panel registry", () => {
  it.each(KINDS)("has a component for %s", (kind) => {
    expect(componentOf(samples[kind])).toBeDefined()
  })

  it.each(KINDS)("has a title and an icon for %s", (kind) => {
    const look = lookOf(samples[kind])
    expect(look.title.length).toBeGreaterThan(0)
    expect(look.icon.length).toBeGreaterThan(0)
  })

  it.each(KINDS)("reports the kind of %s", (kind) => {
    expect(kindOf(samples[kind])).toBe(kind)
  })

  it.each(KINDS)("puts %s into a column that exists", (kind) => {
    expect(PANEL_ROLES).toContain(roleOf(samples[kind]))
  })

  // The panel of connections has no parameters: closing it would leave a
  // column that could say nothing about how to get it back. See T3.
  it("offers no cross on the panel of connections", () => {
    expect(lookOf(samples.connectors).closable).toBe(false)
  })

  it.each(["catalog", "rows", "content", "structure", "chart"] as PanelKind[])(
    "lets %s be closed",
    (kind) => {
      expect(lookOf(samples[kind]).closable).not.toBe(false)
    }
  )

  it.each(KINDS)("accepts a stored %s panel", (kind) => {
    expect(panelSchema.safeParse(samples[kind]).success).toBe(true)
  })

  it("refuses a panel of a kind it does not know", () => {
    expect(panelSchema.safeParse({ id: "x", kind: "sql" }).success).toBe(false)
  })

  it("gives a data tab the name of the node and nothing else", () => {
    // The connection used to stand beside it. It moved into the tooltip when
    // the icon started leading to the catalog: the tab is a fifth of a narrow
    // column and the node is what the eye looks for.
    const look = lookOf(samples.rows)
    expect(look.title).toBe("orders")
    expect(look.subtitle).toBeUndefined()
  })

  it("still says which connection a data tab came from, in the tooltip", () => {
    // Two `users` from two databases are otherwise the same tab. The tooltip
    // is needed anyway, since the icon no longer does what it used to.
    expect(lookOf(samples.rows).iconTooltip).toContain("local pg")
  })

  it("draws a data tab with the icon of its source rather than a generic one", () => {
    expect(lookOf(samples.rows).icon).toBe(adapterIcon("postgres"))
    expect(lookOf(samples.rows).icon).not.toBe(lookOf(samples.connectors).icon)
  })

  it("draws a catalog tab with the icon of its source rather than a generic one", () => {
    expect(lookOf(samples.catalog).icon).toBe(adapterIcon("postgres"))
    expect(lookOf(samples.catalog).icon).not.toBe(lookOf(samples.connectors).icon)
  })

  // Both tabs offer their icon, and they offer different things: from a
  // catalog the connection itself is what there is to reach, from a table it
  // is the catalog the table came from. Editing a connection has two other
  // ways in; reaching the catalog of one table has none.
  it("lets the icon of a catalog tab open the window of that connection", () => {
    expect(lookOf(samples.catalog).iconTooltip).toBe("Edit connection")
  })

  it("lets the icon of a data tab lead to the catalog it came from", () => {
    expect(lookOf(samples.rows).iconTooltip).toContain("Show in catalog")
  })

  it("leaves the icon of the connections tab inert", () => {
    expect(lookOf(samples.connectors).iconTooltip).toBeUndefined()
  })

  it("refuses a rows panel that does not say whose it is", () => {
    expect(
      panelSchema.safeParse({
        id: "x",
        kind: "rows",
        connectorId: "c1",
        nodeId: "n",
        title: "t",
      }).success
    ).toBe(false)
  })

  it("refuses a rows panel with no node", () => {
    expect(
      panelSchema.safeParse({ id: "x", kind: "rows", connectorId: "c1", title: "t" }).success
    ).toBe(false)
  })

  it("has nothing to put in the column of catalogs, so it never appears empty", () => {
    // A column appears with what goes in it: there is no view of a middle
    // column with no catalog in it, and the engine leaves such a column off
    // the screen. See P5.
    expect(emptyOf(roleOf(samples.catalog))).toBeNull()
  })

  it("puts the scene in the column of data, which is therefore always there", () => {
    expect(emptyOf(roleOf(samples.rows))).not.toBeNull()
  })

  it("has nothing to say about a role it does not know", () => {
    expect(emptyOf("sql")).toBeNull()
  })

  it("keeps the connections reachable while their column is pushed aside", () => {
    expect(collapsedOf(samples.connectors)).not.toBeNull()
  })

  it.each(["catalog", "rows", "content", "structure", "chart"] as PanelKind[])(
    "has nothing worth forty pixels for %s",
    (kind) => {
      expect(collapsedOf(samples[kind])).toBeNull()
    }
  )

  it("answers with the same component every time it is asked", () => {
    /* The engine renders this on every frame; a fresh wrapper each time would
       be a different component each time. */
    expect(collapsedOf(samples.connectors)).toBe(collapsedOf(samples.connectors))
  })

  it("names the connections that have a catalog open", () => {
    // The list shows two states now: open, and the one being looked at. See P7.
    const other = {
      ...samples.catalog,
      id: catalogPanelId("c2"),
      connectorId: "c2",
    } as Panel
    expect(openConnectorIds([samples.connectors, samples.catalog, other, samples.rows])).toEqual(
      new Set(["c1", "c2"])
    )
  })

  it("names none while no catalog is open", () => {
    expect(openConnectorIds([samples.connectors])).toEqual(new Set())
  })

  it("gives the same panel of a table the same id every time", () => {
    expect(rowsPanelId("c1", "public.orders")).toBe(rowsPanelId("c1", "public.orders"))
    expect(rowsPanelId("c1", "public.orders")).not.toBe(rowsPanelId("c2", "public.orders"))
  })

  it("identifies two representations of one node as different work", () => {
    expect(contentPanelId("c1", "people.json", "json")).not.toBe(
      contentPanelId("c1", "people.json", "jsonl")
    )
    expect(contentPanelId("c1", "people.json", "json")).not.toBe(rowsPanelId("c1", "people.json"))
    expect(contentPanelId("c1", "people.json", "json")).not.toBe(
      contentPanelId("c1", "people.json", "image")
    )
  })

  it("accepts an image as bounded content with its own component and icon", () => {
    const panel: Panel = {
      id: contentPanelId("c1", "logo.png", "image"),
      kind: "content",
      connectorId: "c1",
      nodeId: "logo.png",
      title: "logo.png",
      connectorName: "my files",
      adapterType: "file",
      representation: "image",
    }

    expect(panelSchema.safeParse(panel).success).toBe(true)
    expect(componentOf(panel)).toBeDefined()
    expect(lookOf(panel).icon).toBe("image")
  })

  it("accepts source-issued SQL as read-only content with its own component", () => {
    const panel: Panel = {
      id: contentPanelId("c1", "public.orders", "sql"),
      kind: "content",
      connectorId: "c1",
      nodeId: "public.orders",
      title: "orders",
      connectorName: "local pg",
      adapterType: "postgres",
      representation: "sql",
      tableTitle: "View as table",
    }

    expect(panelSchema.safeParse(panel).success).toBe(true)
    expect(componentOf(panel)).toBeDefined()
    expect(lookOf(panel).icon).toBe("code")
    expect(lookOf(panel).reloadTooltip).toBe("Re-read this DDL")
  })

  it("puts structure in the column of work", () => {
    expect(
      roleOf({
        id: "s",
        kind: "structure",
        connectorId: "c1",
        nodeId: "public.orders",
        title: "orders",
        connectorName: "db",
        adapterType: "postgres",
      })
    ).toBe("work")
  })

  it("identifies a structure panel by what it shows", () => {
    expect(structurePanelId("c1", "public.orders")).toBe(structurePanelId("c1", "public.orders"))
    expect(structurePanelId("c1", "public.orders")).not.toBe(rowsPanelId("c1", "public.orders"))
  })

  it("puts a bounded chart view in the column of work", () => {
    expect(roleOf(samples.chart)).toBe("work")
    expect(lookOf(samples.chart).title).toBe("orders chart")
  })

  it("distinguishes a chart tab from its source and rows", () => {
    expect(lookOf(samples.chart).icon).toBe("insert_chart")
    expect(lookOf(samples.chart).icon).not.toBe(adapterIcon("postgres"))
    expect(lookOf(samples.chart).iconTooltip).toBe("local pg · Chart")
  })

  it("identifies a chart by its complete view key", () => {
    expect(chartPanelId("one-view")).toBe(chartPanelId("one-view"))
    expect(chartPanelId("one-view")).not.toBe(chartPanelId("another-view"))
  })

  it("refuses a stored chart with an unbounded page", () => {
    expect(
      panelSchema.safeParse({
        ...samples.chart,
        request: { node_id: "public.orders", limit: 501, offset: 0 },
      }).success
    ).toBe(false)
  })

  it("refuses a stored chart whose visible columns are not a real ordered set", () => {
    expect(panelSchema.safeParse({ ...samples.chart, columns: ["total", "total"] }).success).toBe(
      false
    )
    expect(panelSchema.safeParse({ ...samples.chart, columns: [""] }).success).toBe(false)
  })
})
