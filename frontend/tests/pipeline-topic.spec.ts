import { randomUUID } from "node:crypto"

import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { signedApi } from "./utils/search"
import { requireE2EService } from "./utils/services"
import { deleteConnector } from "./utils/workspace"

/**
 * A topic in the middle of a pipeline (D312): a link reads it on from where
 * it stopped, through a consumer group of its own, so each run adds only
 * what arrived since the last.
 */

type Api = { base: string; headers: Record<string, string> }

function row(page: Page, text: string): Locator {
  return page.getByTestId("pipeline-canvas").locator('[data-testid^="graph-port-"]', { hasText: text })
}

async function drawLink(page: Page, from: Locator, to: Locator) {
  const start = await from.boundingBox()
  const end = await to.boundingBox()
  if (start === null || end === null) throw new Error("A row to join is not on screen")
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
  await page.mouse.down()
  await page.mouse.move(end.x + end.width / 2, end.y + end.height / 2, { steps: 12 })
  await page.mouse.up()
}

async function connectorId(page: Page, api: Api, name: string): Promise<string> {
  const listed = await page.request.get(`${api.base}/connectors/`, { headers: api.headers })
  expect(listed.ok()).toBeTruthy()
  const body = (await listed.json()) as { data?: { id: string; name: string }[] } | { id: string; name: string }[]
  const all = Array.isArray(body) ? body : body.data ?? []
  const found = all.find((one) => one.name === name)
  if (found === undefined) throw new Error(`No connection named ${name}`)
  return found.id
}

async function sql(page: Page, api: Api, connector: string, text: string) {
  const runId = randomUUID()
  const started = await page.request.post(`${api.base}/queries/runs`, {
    headers: api.headers,
    data: { run_id: runId, connector_id: connector, text, mode: "auto_commit", confirm_write: true, confirm_high_risk: true },
  })
  expect(started.ok(), await started.text()).toBeTruthy()
  await expect.poll(async () => {
    const read = await page.request.get(`${api.base}/queries/runs/${runId}`, { headers: api.headers })
    return ((await read.json()) as { status: string }).status
  }, { timeout: 15_000 }).toBe("succeeded")
}

async function send(page: Page, api: Api, kafka: string, topic: string, ids: number[]) {
  for (const id of ids) {
    const sent = await page.request.post(`${api.base}/connectors/${kafka}/rows`, {
      headers: api.headers,
      data: { node_id: `topic:${topic}`, values: [{ column: "value", value: JSON.stringify({ id }) }] },
    })
    expect(sent.ok(), await sent.text()).toBeTruthy()
  }
}

test("reads a topic into a table, only what is new at each run", async ({ page }) => {
  await requireE2EService("kafka")
  const stamp = Date.now()
  const database = `e2e-topic-db-${stamp}`
  const broker = `e2e-topic-kafka-${stamp}`
  const topic = `e2e.arrivals.${stamp}`
  const table = `e2e_arrived_${stamp}`
  await login(page)
  const api = await signedApi(page)

  const made = await page.request.post(`${api.base}/connectors/`, {
    headers: api.headers,
    data: { name: broker, adapter_type: "kafka", options: { bootstrap_servers: "kafka:9092", auth_method: "none" } },
  })
  expect(made.ok(), await made.text()).toBeTruthy()
  const kafka = ((await made.json()) as { id: string }).id
  const topicMade = await page.request.post(`${api.base}/connectors/${kafka}/actions/new_topic`, {
    headers: api.headers,
    data: { node_id: "topics", params: { name: topic, partitions: 1, settings: "" } },
  })
  expect(topicMade.ok(), await topicMade.text()).toBeTruthy()
  await send(page, api, kafka, topic, [1, 2, 3])

  await createPostgresConnector(page, database)
  const postgres = await connectorId(page, api, database)
  await sql(page, api, postgres, `CREATE TABLE public.${table} (value text)`)

  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()

  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${broker}`).click()
  await picker.getByTestId("catalog-node-Topics").click()
  await picker.getByTestId(`catalog-check-${topic}`).click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-node-public").click()
  await picker.getByTestId(`catalog-check-${table}`).click()
  await picker.getByTestId("card-picker-done").click()

  // The one way out of a topic: its pairing opens at once.
  await drawLink(page, row(page, topic), row(page, table))
  const panel = page.getByTestId("link-panel")
  await expect(panel.getByTestId("link-panel-sentence")).toContainText("Add new messages to a table")
  const pairing = page.getByTestId("grid-import-dialog")
  await expect(pairing).toBeVisible()
  await pairing.getByTestId("grid-import-pair-value").click()
  await page.getByRole("option", { name: "value", exact: true }).click()
  await pairing.getByTestId("grid-import-run").click()
  await expect(pairing).toHaveCount(0)

  // The server names the link's group once the pipeline is saved.
  await page.getByTestId("pipeline-run").click()
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("3 new messages added", { timeout: 30_000 })
  await expect(panel.getByTestId("link-panel-reader")).toContainText("dataplayer-link-")
  await expect(panel.getByTestId("link-panel-start")).toBeVisible()

  await send(page, api, kafka, topic, [4, 5])
  await page.getByTestId("pipeline-run").click()
  await expect(result).toContainText("2 new messages added", { timeout: 30_000 })
  await page.screenshot({ path: "test-results/pipeline-topic.png" })

  await page.getByTestId("pipeline-run").click()
  await expect(result).toContainText("Nothing new since the last run", { timeout: 30_000 })

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await sql(page, api, postgres, `DROP TABLE public.${table}`)
  await page.request.post(`${api.base}/connectors/${kafka}/actions/delete_topic`, {
    headers: api.headers,
    data: { node_id: `topic:${topic}`, params: {} },
  })
  await page.getByTestId("space-data").click()
  await deleteConnector(page, database)
  await deleteConnector(page, broker)
})

test("reads a topic into a table its link makes, keyed so each message is kept once (D313)", async ({ page }) => {
  await requireE2EService("kafka")
  const stamp = Date.now()
  const database = `e2e-topic-new-db-${stamp}`
  const broker = `e2e-topic-new-kafka-${stamp}`
  const topic = `e2e.made.${stamp}`
  const table = `e2e_made_${stamp}`
  await login(page)
  const api = await signedApi(page)

  const made = await page.request.post(`${api.base}/connectors/`, {
    headers: api.headers,
    data: { name: broker, adapter_type: "kafka", options: { bootstrap_servers: "kafka:9092", auth_method: "none" } },
  })
  expect(made.ok(), await made.text()).toBeTruthy()
  const kafka = ((await made.json()) as { id: string }).id
  const topicMade = await page.request.post(`${api.base}/connectors/${kafka}/actions/new_topic`, {
    headers: api.headers,
    data: { node_id: "topics", params: { name: topic, partitions: 1, settings: "" } },
  })
  expect(topicMade.ok(), await topicMade.text()).toBeTruthy()
  await send(page, api, kafka, topic, [1, 2, 3])
  await createPostgresConnector(page, database)
  const postgres = await connectorId(page, api, database)

  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()

  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${broker}`).click()
  await picker.getByTestId("catalog-node-Topics").click()
  await picker.getByTestId(`catalog-check-${topic}`).click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("card-picker-done").click()

  // Drawn to a schema: the table is made, its window opens at once with
  // every column of the topic, partition and offset among them.
  await drawLink(page, row(page, topic), row(page, "public"))
  const panel = page.getByTestId("link-panel")
  await expect(panel.getByTestId("link-panel-sentence")).toContainText("Add new messages to a new table")
  const window = page.getByTestId("grid-create-table-dialog")
  await expect(window).toBeVisible()
  await window.getByTestId("grid-create-table-name").fill(table)
  await window.getByTestId("grid-create-table-run").click()
  await expect(window).toHaveCount(0)
  // What it makes is a row of the card before it runs (D178).
  await expect(page.getByTestId("pipeline-canvas")).toContainText(table)

  await page.getByTestId("pipeline-run").click()
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("3 new messages added", { timeout: 30_000 })
  await expect(result).toContainText("the table was made with a key on partition and offset")

  await send(page, api, kafka, topic, [4, 5])
  await page.getByTestId("pipeline-run").click()
  await expect(result).toContainText("2 new messages added", { timeout: 30_000 })
  await expect(result).not.toContainText("the table was made")
  await page.screenshot({ path: "test-results/pipeline-topic-new-table.png" })

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await sql(page, api, postgres, `DROP TABLE public.${table}`)
  await page.request.post(`${api.base}/connectors/${kafka}/actions/delete_topic`, {
    headers: api.headers,
    data: { node_id: `topic:${topic}`, params: {} },
  })
  await page.getByTestId("space-data").click()
  await deleteConnector(page, database)
  await deleteConnector(page, broker)
})
