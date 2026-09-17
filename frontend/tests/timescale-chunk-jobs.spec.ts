import { expect, test } from "@playwright/test"

import type { ActionInfo, ActionPreview, ActionRequest, JobPublic, TableNode } from "../src/client"
import { catalogAction, catalogCheck } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

const TARGET = "lab.metrics"
const FINGERPRINT = "d".repeat(64)
const JOB_ID = "22345678-1234-4123-8123-123456789012"
const SUMMARY = 'Compress 3 chunks of "lab"."metrics" as a job'

const table: TableNode = {
  id: TARGET, name: "metrics", kind: "table", has_children: false,
  summarizable: true, describable: false,
  representations: [{ kind: "table", title: "View as table" }],
  specialization: { kind: "timescale_hypertable" },
}

function compressAction(nodeIds: (string | null)[]): ActionInfo {
  const ticked = nodeIds.length === 1 && nodeIds[0] === TARGET
  return {
    name: "timescale_compress_chunks", title: "Compress chunks",
    applicable: ticked, available_node_ids: ticked ? [TARGET] : [],
    unavailable_reason: ticked ? null : "Tick a row to use this",
    destructive: false, question: null,
    takes_file: false, takes_many_files: false, previews: true, requires_plan_review: true,
    produces_job: true, takes_set: false, previews_set: false, downloads: false,
    acts_on: "node", offered_in: "catalog",
    params_schema: {
      type: "object", title: "ChunkWindowParams", additionalProperties: false, required: ["ends_by"],
      properties: {
        ends_by: {
          type: "string", format: "date-time", title: "Chunks ending at or before",
          examples: ["2026-01-15T00:00:00Z"],
        },
        starts_from: {
          anyOf: [{ type: "string", format: "date-time" }, { type: "null" }], default: null,
          title: "and starting at or after", examples: ["2026-01-01T00:00:00Z"],
        },
      },
    },
  }
}

function target(name: string, outcome: string, message: string | null = null) {
  return { target: { schema_name: "_timescaledb_internal", name }, outcome, message, observed: null }
}

function chunkJob(
  connectorId: string, state: JobPublic["state"], targets: ReturnType<typeof target>[],
  message: string | null,
): JobPublic {
  const now = new Date().toISOString()
  return {
    id: JOB_ID, kind: "source.operation", subject_id: connectorId,
    parameters: {
      version: 1, action: "timescale_compress_chunks", title: "Compress chunks", node_id: TARGET,
      params: {}, requires: "structure", connector_revision: null, summary: SUMMARY,
      unit_fingerprint: "e".repeat(64), targets,
    },
    state, step: state === "running" ? "carrying out the reviewed plan" : null,
    step_index: 2, step_count: 3, message,
    created_at: now, started_at: now, finished_at: state === "running" ? null : now,
  }
}

test("a chunk job is reviewed, accepted, followed and explained again after a reload", async ({ page }) => {
  const name = `e2e-chunk-jobs-${Date.now()}`
  const started: ActionRequest[] = []
  let connectorId = ""
  let listed: JobPublic[] = []

  // Transport fixtures: what the browser draws of an owned job. Chunk
  // conversion itself is covered by the isolated compatibility suite.
  await page.route("**/api/v1/connectors/*/catalog**", async (route) => {
    const url = new URL(route.request().url())
    const schema = { id: "lab", name: "lab", kind: "schema", has_children: true, representations: [] }
    await route.fulfill({ json: url.pathname.endsWith("/path")
      ? [schema, table]
      : url.searchParams.get("node_id") ? [table] : [schema] })
  })
  await page.route("**/api/v1/connectors/*/actions", async (route) => {
    const body = route.request().postDataJSON() as { node_ids?: (string | null)[] | null }
    await route.fulfill({ json: [compressAction(body.node_ids ?? [null])] })
  })
  await page.route("**/api/v1/connectors/*/actions/timescale_compress_chunks/preview", async (route) => {
    const request = route.request().postDataJSON() as ActionRequest
    const preview: ActionPreview = request.params?.ends_by
      ? {
          summary: SUMMARY,
          items: ["Whole chunks from the earliest chunk to 2026-01-15T00:00:00+00:00"],
          fingerprint: FINGERPRINT,
        }
      : { summary: "Say which chunks: the window needs its end", blocked: true }
    await route.fulfill({ json: preview })
  })
  await page.route("**/api/v1/connectors/*/actions/timescale_compress_chunks/jobs", async (route) => {
    started.push(route.request().postDataJSON() as ActionRequest)
    connectorId = new URL(route.request().url()).pathname.split("/")[4] ?? ""
    listed = [chunkJob(connectorId, "running", [
      target("_hyper_1_1_chunk", "completed"),
      target("_hyper_1_2_chunk", "running"),
      target("_hyper_1_3_chunk", "pending"),
    ], null)]
    await route.fulfill({ status: 202, json: listed[0] })
  })
  await page.route((url) => url.pathname === "/api/v1/jobs/", async (route) => {
    await route.fulfill({ json: {
      data: listed, count: listed.length,
      active_count: listed.filter((item) => item.state === "running").length,
    } })
  })

  await login(page)
  await createPostgresConnector(page, name)
  try {
    await openConnector(page, name)
    await catalogCheck(page, "metrics").click()
    await catalogAction(page, "timescale_compress_chunks")

    const dialog = page.getByTestId("action-dialog")
    const submit = page.getByTestId("action-submit")
    await expect(dialog).toBeVisible()
    await expect(submit).toBeDisabled()
    await page.getByTestId("field-ends_by").fill("2026-01-15T00:00:00Z")
    await expect(page.getByTestId("action-preview")).toContainText(SUMMARY)
    await expect(submit).toBeEnabled()

    // Accepted, not awaited: the window closes and the work is the server's.
    await submit.click()
    await expect(dialog).toHaveCount(0)
    expect(started).toEqual([{
      node_id: TARGET, params: { ends_by: "2026-01-15T00:00:00Z", starts_from: null },
      reviewed_fingerprint: FINGERPRINT,
    }])

    const indicator = page.getByTestId("activity-indicator")
    const sheet = page.getByTestId("activity-panel")
    // Icon-only: the button carries the waiting count and names the step on
    // hover; the job's title lives in the sheet it opens.
    await expect(indicator.getByTestId("activity-count")).toHaveText("1")
    await indicator.hover()
    await expect(page.locator(".app-tooltip")).toContainText("carrying out the reviewed plan (2 of 3)")
    await indicator.click()
    await expect(sheet).toContainText(`Compress chunks · ${name}`)
    await expect(sheet).toContainText("1 of 3 processed")
    await expect(sheet).toContainText("Now: _timescaledb_internal._hyper_1_2_chunk")
    await page.keyboard.press("Escape")

    // It ended while nobody was looking; a reload reads the same job back.
    listed = [chunkJob(connectorId, "failed", [
      target("_hyper_1_1_chunk", "completed"),
      target("_hyper_1_2_chunk", "refused", "This chunk is in use; nothing was converted"),
      target("_hyper_1_3_chunk", "pending"),
    ], `${SUMMARY}: 1 done, 1 refused, 1 not attempted. It stopped at the first target that did not complete`)]
    await page.reload()
    await indicator.click()
    await expect(sheet).toContainText("1 done, 1 refused, 1 not attempted")
    await expect(sheet).toContainText(
      "_timescaledb_internal._hyper_1_2_chunk: This chunk is in use; nothing was converted"
    )
    await expect(sheet).toContainText("2 of 3 processed")
    await page.keyboard.press("Escape")
  } finally {
    await deleteConnector(page, name)
  }
})
