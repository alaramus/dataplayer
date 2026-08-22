import { describe, expect, it } from "vitest"

import { catalogPanelId, componentOf, kindOf, lookOf, panelSchema, rowsPanelId } from "./panels"
import type { Panel, PanelKind } from "./panels"

const KINDS: PanelKind[] = ["connectors", "catalog", "rows"]

const samples: Record<PanelKind, Panel> = {
  connectors: { id: "connectors", kind: "connectors" },
  catalog: { id: catalogPanelId("c1"), kind: "catalog", connectorId: "c1", title: "local pg" },
  rows: {
    id: rowsPanelId("c1", "public.orders"),
    kind: "rows",
    connectorId: "c1",
    nodeId: "public.orders",
    title: "orders",
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

  it.each(KINDS)("accepts a stored %s panel", (kind) => {
    expect(panelSchema.safeParse(samples[kind]).success).toBe(true)
  })

  it("refuses a panel of a kind it does not know", () => {
    expect(panelSchema.safeParse({ id: "x", kind: "sql" }).success).toBe(false)
  })

  it("refuses a rows panel with no node", () => {
    expect(
      panelSchema.safeParse({ id: "x", kind: "rows", connectorId: "c1", title: "t" }).success
    ).toBe(false)
  })

  it("gives the same panel of a table the same id every time", () => {
    expect(rowsPanelId("c1", "public.orders")).toBe(rowsPanelId("c1", "public.orders"))
    expect(rowsPanelId("c1", "public.orders")).not.toBe(rowsPanelId("c2", "public.orders"))
  })
})
