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
      {
        id: "query:draft:abc",
        kind: "query",
        draftId: "abc",
        connectorId: "one",
        title: null,
        connectorName: "Shop",
      },
      { id: "queries", kind: "queries" },
      { id: "result:xyz", kind: "result", connectorId: "one", resultId: "xyz", title: "Q1" },
    ]

    // A console's SQL, the query library and a captured result never reach
    // the model — no tool reads them — so offering them would invite the
    // model to pretend it saw them.
    expect(screenContexts(panels)).toEqual([
      {
        panel_id: "rows:one:orders",
        label: "orders · Rows",
        kind: "rows",
        connector_id: "one",
        node_id: "orders",
      },
    ])
  })
})
