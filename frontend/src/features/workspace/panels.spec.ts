import { describe, expect, it } from "vitest"

import { adapterIcon } from "@/features/connectors/adapters"

import {
  catalogPanelId,
  collapsedOf,
  componentOf,
  emptyOf,
  kindOf,
  lookOf,
  openConnectorIds,
  panelSchema,
  PANEL_ROLES,
  roleOf,
  rowsPanelId,
} from "./panels"
import type { Panel, PanelKind } from "./panels"

const KINDS: PanelKind[] = ["connectors", "catalog", "rows"]

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

  it.each(["catalog", "rows"] as PanelKind[])("lets %s be closed", (kind) => {
    expect(lookOf(samples[kind]).closable).not.toBe(false)
  })

  it.each(KINDS)("accepts a stored %s panel", (kind) => {
    expect(panelSchema.safeParse(samples[kind]).success).toBe(true)
  })

  it("refuses a panel of a kind it does not know", () => {
    expect(panelSchema.safeParse({ id: "x", kind: "sql" }).success).toBe(false)
  })

  it("says which connection a data tab came from, quietly beside the node", () => {
    // Two connections of one type look alike, and the node is what the eye
    // looks for: the name stays in front and the connection follows. See P8.
    const look = lookOf(samples.rows)
    expect(look.title).toBe("orders")
    expect(look.subtitle).toBe("local pg")
  })

  it("draws a data tab with the icon of its source rather than a generic one", () => {
    expect(lookOf(samples.rows).icon).toBe(adapterIcon("postgres"))
    expect(lookOf(samples.rows).icon).not.toBe(lookOf(samples.connectors).icon)
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

  it.each(["catalog", "rows"] as PanelKind[])(
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
})
