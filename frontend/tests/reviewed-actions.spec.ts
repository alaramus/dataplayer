import { expect, test } from "@playwright/test"

import type { ActionInfo, ActionPreview, ActionRequest, ActionResult, TableNode } from "../src/client"
import { catalogAction, catalogCheck } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

const TARGET = "lab.metrics"
const QUESTION = "TimescaleDB will keep dropping old chunks by itself, even after this session ends. Set this policy?"

const table: TableNode = {
  id: TARGET, name: "metrics", kind: "table", has_children: false,
  summarizable: true, describable: false,
  representations: [{ kind: "table", title: "View as table" }],
  specialization: { kind: "timescale_hypertable" },
}

function retentionAction(nodeIds: (string | null)[]): ActionInfo {
  const ticked = nodeIds.length === 1 && nodeIds[0] === TARGET
  return {
    name: "timescale_set_retention_policy", title: "Set retention policy",
    applicable: ticked, available_node_ids: ticked ? [TARGET] : [],
    unavailable_reason: ticked ? null : "Tick a row to use this",
    destructive: true, question: QUESTION,
    takes_file: false, takes_many_files: false, previews: true, requires_plan_review: true,
    takes_set: false, previews_set: false, downloads: false, acts_on: "node", offered_in: "catalog",
    params_schema: {
      type: "object", title: "RetentionParams", additionalProperties: false,
      required: ["amount", "unit"],
      properties: {
        amount: {
          type: "integer", exclusiveMinimum: 0, maximum: 2147483647,
          title: "Drop chunks older than", group: "general", row: "threshold",
        },
        unit: {
          type: "string", enum: ["hour", "day", "week", "month", "year"],
          title: "Unit", group: "general", row: "threshold",
        },
      },
    },
  }
}

interface Deferred {
  promise: Promise<void>
  release: () => void
}

function deferred(): Deferred {
  let release = () => {}
  const promise = new Promise<void>((resolve) => { release = resolve })
  return { promise, release }
}

test("a reviewed plan gates the action and a refused run asks for a new review", async ({ page }) => {
  const name = `e2e-reviewed-${Date.now()}`
  const previews: ActionRequest[] = []
  const runs: ActionRequest[] = []
  // A refused run stands for a source that changed after review: every plan
  // drawn after it is a different plan.
  let generation = 0
  let held: Deferred | null = null

  // Transport fixtures exercise the browser contract of a reviewed action; the
  // source semantics of each plan are covered by the isolated compatibility suite.
  await page.route("**/api/v1/connectors/*/catalog**", async (route) => {
    const url = new URL(route.request().url())
    const schema = { id: "lab", name: "lab", kind: "schema", has_children: true, representations: [] }
    await route.fulfill({ json: url.pathname.endsWith("/path")
      ? [schema, table]
      : url.searchParams.get("node_id") ? [table] : [schema] })
  })
  await page.route("**/api/v1/connectors/*/actions", async (route) => {
    const body = route.request().postDataJSON() as { node_ids?: (string | null)[] | null }
    await route.fulfill({ json: [retentionAction(body.node_ids ?? [null])] })
  })
  await page.route("**/api/v1/connectors/*/actions/timescale_set_retention_policy/preview", async (route) => {
    const request = route.request().postDataJSON() as ActionRequest
    previews.push(request)
    const amount = request.params?.amount
    if (held !== null && amount === 20) {
      const waiting = held
      held = null
      await waiting.promise
    }
    let preview: ActionPreview
    if (request.params?.unit === "hour") {
      preview = { summary: "Date dimensions require whole days, weeks, months or years", blocked: true }
    } else {
      const seed = amount === 10 ? "a" : generation === 0 ? "b" : "c"
      preview = {
        summary: 'Set the retention policy for "lab"."metrics"',
        items: [
          generation === 0
            ? "No retention policy exists yet"
            : "Replaces job 1000, which drops chunks older than 30 days",
          `New policy: drop chunks older than ${String(amount)} ${String(request.params?.unit)}`,
        ],
        fingerprint: seed.repeat(64),
      }
    }
    await route.fulfill({ json: preview })
  })
  await page.route("**/api/v1/connectors/*/actions/timescale_set_retention_policy", async (route) => {
    runs.push(route.request().postDataJSON() as ActionRequest)
    if (runs.length === 1) {
      generation += 1
      await route.fulfill({
        status: 409,
        json: { detail: { message: "The operation plan changed; review it again", reason: "conflict" } },
      })
      return
    }
    const result: ActionResult = {
      message: "Retention policy set: TimescaleDB drops chunks older than 20 year on its own schedule",
      reload_node_ids: ["lab", TARGET],
    }
    await route.fulfill({ json: result })
  })

  await login(page)
  await createPostgresConnector(page, name)
  try {
    await openConnector(page, name)
    await catalogCheck(page, "metrics").click()
    await catalogAction(page, "timescale_set_retention_policy")

    const dialog = page.getByTestId("action-dialog")
    const submit = page.getByTestId("action-submit")
    const plan = page.getByTestId("action-preview")
    await expect(dialog).toBeVisible()
    await expect(page.getByTestId("action-confirmation")).toHaveText(QUESTION)
    await expect(submit).toBeDisabled()

    await page.getByTestId("field-amount").fill("10")
    await page.getByTestId("field-unit").click()
    await page.getByRole("option", { name: "year", exact: true }).click()
    await expect(plan).toContainText("New policy: drop chunks older than 10 year")
    await expect(submit).toBeEnabled()

    // A changed form voids the plan at once, before the source has answered.
    held = deferred()
    const waiting = held
    await page.getByTestId("field-amount").fill("20")
    await expect(submit).toBeDisabled()
    await expect(plan).toHaveCount(0)
    await expect.poll(() => previews.at(-1)?.params?.amount).toBe(20)
    await expect(submit).toBeDisabled()
    waiting.release()
    await expect(plan).toContainText("New policy: drop chunks older than 20 year")
    await expect(submit).toBeEnabled()

    // A plan the source refuses is shown and cannot be applied.
    await page.getByTestId("field-unit").click()
    await page.getByRole("option", { name: "hour", exact: true }).click()
    await expect(plan).toContainText("Date dimensions require whole days")
    await expect(submit).toBeDisabled()
    await page.getByTestId("field-unit").click()
    await page.getByRole("option", { name: "year", exact: true }).click()
    await expect(plan).toContainText("No retention policy exists yet")
    await expect(submit).toBeEnabled()

    // The reviewed fingerprint travels beside the parameters, never inside them.
    await submit.click()
    await expect.poll(() => runs.length).toBe(1)
    expect(runs[0]).toEqual({
      node_id: TARGET, params: { amount: 20, unit: "year" }, reviewed_fingerprint: "b".repeat(64),
    })

    // Refused: the form stays, the plan is drawn again, and nothing is retried.
    await expect(page.getByTestId("action-error")).toContainText("review it again")
    await expect(dialog).toBeVisible()
    await expect(plan).toContainText("Replaces job 1000, which drops chunks older than 30 days")
    await expect(submit).toBeEnabled()
    expect(runs).toHaveLength(1)

    await submit.click()
    await expect.poll(() => runs.length).toBe(2)
    expect(runs[1]?.reviewed_fingerprint).toBe("c".repeat(64))
    await expect(dialog).toHaveCount(0)
  } finally {
    await deleteConnector(page, name)
  }
})
