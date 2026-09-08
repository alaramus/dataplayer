import { expect, test } from "@playwright/test"

import type { FetchRequest, FetchResult, NodeSummary, ReportNode, TableNode } from "../src/client"
import { catalogAction, catalogCheck, openNode } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

test("Timescale Details opens an editable scoped Chunks report with writes disabled", async ({ page }) => {
  const name = `e2e-timescale-navigation-${Date.now()}`
  const table: TableNode = {
    id: "lab.metrics", name: "metrics", kind: "table", has_children: false,
    summarizable: true, describable: false,
    representations: [{ kind: "table", title: "View as table" }],
    specialization: { kind: "timescale_hypertable" },
  }
  const chunks: ReportNode = {
    id: "pg_dataplayer.timescale.v1.chunks", name: "Chunks", kind: "report",
    has_children: false, representations: [{ kind: "table", title: "View as table" }],
  }
  const filters: NonNullable<FetchRequest["filters"]> = [
    { column: "hypertable_schema", op: "eq", value: "lab" },
    { column: "hypertable_name", op: "eq", value: "metrics" },
  ]
  const summary: NodeSummary = {
    node_id: table.id, name: table.name, kind: "table",
    contents: {
      kind: "relation", relation_kind: "table", schema_name: "lab",
      columns: 1, indexes: 0, constraints: 0, specialization: { kind: "timescale_hypertable" },
    },
    related_views: [{ node: chunks, filters }],
  }
  const requests: FetchRequest[] = []
  // Transport fixtures exercise the browser contract; source semantics are
  // covered separately by the isolated compatibility suite.
  await page.route("**/api/v1/connectors/*/catalog**", async (route) => {
    const url = new URL(route.request().url())
    const schema = { id: "lab", name: "lab", kind: "schema", has_children: true, representations: [] }
    await route.fulfill({ json: url.pathname.endsWith("/path")
      ? [schema, table]
      : url.searchParams.get("node_id") ? [table] : [schema] })
  })
  await page.route("**/api/v1/connectors/*/node-summary**", (route) => route.fulfill({ json: summary }))
  await page.route("**/api/v1/connectors/*/actions", (route) => route.fulfill({ json: [] }))
  await page.route("**/api/v1/connectors/*/fetch**", async (route) => {
    const request = route.request().postDataJSON() as FetchRequest
    requests.push(request)
    const report = request.node_id === chunks.id
    const result: FetchResult = {
      columns: (report ? ["hypertable_schema", "hypertable_name"] : ["value"]).map((name) => ({
        name, type: { sql: "text", category: "string" }, nullable: false,
        editable: false, insertable: false, filter_operators: ["eq"],
      })),
      rows: report ? [["lab", "metrics"]] : [["9007199254740993"]],
      has_more: false, row_handles: [null], update_supported: false,
      insert_supported: false, delete_supported: false,
      insert_reason: "TimescaleDB relations are read-only in this version",
      delete_reason: "TimescaleDB relations are read-only in this version",
    }
    await route.fulfill({ json: result })
  })
  await login(page)
  await createPostgresConnector(page, name)
  try {
    await openConnector(page, name)
    await openNode(page, "metrics")
    await expect(page.getByTestId("grid-row-0")).toContainText("9007199254740993")
    await expect(page.getByTestId("grid-insert")).toBeDisabled()
    await expect(page.getByTestId("grid-delete")).toBeDisabled()
    await catalogCheck(page, "metrics").click()
    await catalogAction(page, "client:details")
    await expect(page.getByTestId("summary-view")).toContainText("TimescaleDB hypertable")
    await page.getByTestId("summary-related-views").getByRole("button", { name: "Chunks", exact: true }).click()
    await expect.poll(() => requests.find((request) => request.node_id === chunks.id)?.filters).toEqual(filters)
    const editor = page.getByTestId("grid-filter-editor")
    if (!(await editor.isVisible())) await page.getByTestId("grid-filter").click()
    await expect(editor).toContainText("hypertable_schema")
    await expect(editor).toContainText("metrics")
    await page.getByTestId("grid-filter-delete-0").click()
    await expect.poll(() => requests.filter((request) => request.node_id === chunks.id).at(-1)?.filters)
      .toEqual([filters[1]])
  } finally {
    await deleteConnector(page, name)
  }
})
