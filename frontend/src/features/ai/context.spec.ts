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
        label: "Shop · orders · Rows",
        kind: "rows",
        connector_id: "one",
        node_id: "orders",
      },
    ])
  })

  it("omits widget and service-log tabs the backend cannot accept", () => {
    const panels: Panel[] = [
      {
        id: "widget-tab:dash-1:w1:abc",
        kind: "widget",
        dashboardId: "dash-1",
        widget: {
          type: "stat",
          id: "w1",
          title: "CPU",
          layout: { x: 0, y: 0, w: 3, h: 5 },
          series_id: 7,
        },
        rangeSeconds: 900,
        refreshSeconds: 30,
      },
      { id: "service-logs:svc-1", kind: "service-logs", serviceId: "svc-1", serviceName: "warehouse" },
    ]

    expect(screenContexts(panels)).toEqual([])
  })

  it("names the connection, node and panel kind without repeating catalog names", () => {
    const panels: Panel[] = [
      { id: "catalog:one", kind: "catalog", connectorId: "one", title: "Shop", adapterType: "postgres" },
      {
        id: "structure:one:orders",
        kind: "structure",
        connectorId: "one",
        nodeId: "orders",
        title: "orders",
        connectorName: "Shop",
        adapterType: "postgres",
      },
    ]

    expect(screenContexts(panels).map((context) => context.label)).toEqual([
      "Shop · Catalog",
      "Shop · orders · Structure",
    ])
  })
})
