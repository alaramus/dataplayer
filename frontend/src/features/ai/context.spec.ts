import { describe, expect, it } from "vitest"

import type { Panel } from "@/features/workspace/panels"

import { screenContexts } from "./context"

describe("AI screen context", () => {
  it("offers open data tabs and omits the fixed connections panel", () => {
    const panels: Panel[] = [
      { id: "connectors", kind: "connectors" },
      {
        id: "rows:one:orders",
        kind: "rows",
        connectorId: "one",
        nodeId: "orders",
        title: "orders",
        connectorName: "Shop",
        adapterType: "postgres",
      },
      { id: "queries", kind: "queries" },
    ]

    expect(screenContexts(panels)).toEqual([
      {
        panel_id: "rows:one:orders",
        label: "orders · Rows",
        kind: "rows",
        connector_id: "one",
        node_id: "orders",
      },
      { panel_id: "queries", label: "Queries · Queries", kind: "queries" },
    ])
  })
})
