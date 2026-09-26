import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector } from "./utils/workspace"

/**
 * Pipelines (D175, D176): connections dragged, or pressed, onto a canvas
 * become cards of what was ticked in them; rows are joined by links that run
 * as Paste does; the pipeline is kept on the server.
 */

function cards(page: Page, name: string): Locator {
  return page.getByTestId("pipeline-canvas").locator('[data-testid^="graph-node-"]', { hasText: name })
}

/** The next save of the pipeline, started by whatever the caller does next. */
function saved(page: Page) {
  return page.waitForResponse(
    (response) => response.url().includes("/api/v1/pipelines/") && response.request().method() === "PUT"
  )
}

test("lays connections out as cards of what was ticked in them, and keeps them", async ({ page }) => {
  const stamp = Date.now()
  const database = `e2e-pipe-db-${stamp}`
  const files = `e2e-pipe-files-${stamp}`
  const name = `e2e-pipeline-${stamp}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  await page.getByTestId("space-pipelines").click()
  await expect(page.getByTestId("pipelines-space")).toBeVisible()
  const first = page.getByTestId("pipeline-create-first")
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/pipelines") && response.request().method() === "POST"
  )
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await created
  await page.getByTestId("pipeline-rename").click()
  await page.getByTestId("pipeline-rename-input").fill(name)
  const renamed = saved(page)
  await page.getByTestId("pipeline-rename-apply").click()
  await renamed
  await expect(page.getByTestId("pipeline-view")).toContainText(name)

  // Dragged from the list and dropped: its catalog, with ticks.
  const rail = page.getByTestId("pipelines-rail")
  await rail.getByTestId(`connector-${files}`).dragTo(page.getByTestId("pipeline-canvas"))
  const picker = page.getByTestId("card-picker")
  await expect(picker).toBeVisible()
  // The top of personal storage is a place of its own.
  await expect(picker.getByTestId("card-picker-top")).toBeVisible()
  await picker.getByTestId("catalog-check-reports").click()
  await expect(picker.getByTestId("card-picker-chosen-reports")).toBeVisible()
  await picker.getByTestId("card-picker-done").click()
  await expect(picker).toHaveCount(0)
  await expect(cards(page, files)).toHaveCount(1)
  await expect(cards(page, files)).toContainText("reports")

  // Pressed rather than dragged, and walked into: a schema, and a table in it.
  await rail.getByTestId(`connector-${database}`).click()
  await expect(picker.getByTestId("card-picker-top")).toHaveCount(0)
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("catalog-node-public").click()
  await expect(picker.getByTestId("card-picker-where")).toHaveText(`${database} / public`)
  await picker.getByTestId("catalog-check-pipeline").click()
  await expect(picker.getByTestId("card-picker-chosen")).toContainText("2 ticked")
  await page.screenshot({ path: "test-results/pipelines-picker.png" })
  await picker.getByTestId("card-picker-done").click()
  await expect(cards(page, database)).toHaveCount(1)
  await expect(cards(page, database)).toContainText("pipeline")

  // The same connection, a second time.
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("card-picker-done").click()
  await expect(cards(page, database)).toHaveCount(2)

  // A card's settings open the window again on what it holds.
  await page.getByTestId(`pipeline-card-settings-${database}`).first().click()
  await expect(picker.getByTestId("card-picker-chosen")).toContainText("2 ticked")
  await picker.getByTestId("card-picker-chosen-public").getByRole("button").click()
  await expect(picker.getByTestId("card-picker-chosen")).toContainText("1 ticked")
  const edited = saved(page)
  await picker.getByTestId("card-picker-done").click()
  await edited
  await page.screenshot({ path: "test-results/pipelines.png" })

  // Kept: read again, the pipeline is as it was left.
  await page.reload()
  await expect(page.getByTestId("pipeline-view")).toContainText(name)
  await expect(cards(page, database)).toHaveCount(2)
  await expect(cards(page, files)).toContainText("reports")

  const removed = saved(page)
  await page.getByTestId(`pipeline-card-remove-${files}`).click()
  await page.getByTestId("confirm-accept").click()
  await removed
  await expect(cards(page, files)).toHaveCount(0)

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("pipeline-view").or(page.getByTestId("pipeline-create-first"))).toBeVisible()
  await expect(page.getByTestId("pipelines-space")).not.toContainText(name)

  await page.getByTestId("space-data").click()
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

function row(page: Page, text: string): Locator {
  return page.getByTestId("pipeline-canvas").locator('[data-testid^="graph-port-"]', { hasText: text })
}

/** A row dragged onto another with the mouse, as a person draws a link. */
async function drawLink(page: Page, from: Locator, to: Locator) {
  const start = await from.boundingBox()
  const end = await to.boundingBox()
  if (start === null || end === null) throw new Error("A row to join is not on screen")
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
  await page.mouse.down()
  await page.mouse.move(end.x + end.width / 2, end.y + end.height / 2, { steps: 12 })
  await page.mouse.up()
}

test("joins two rows by a link, runs it from the panel below, and hints the others", async ({ page }) => {
  const stamp = Date.now()
  const database = `e2e-link-db-${stamp}`
  const files = `e2e-link-files-${stamp}`
  const csv = `e2e-link-${stamp}.csv`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)
  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()

  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${files}`).click()
  await picker.getByTestId("card-picker-top").click()
  await picker.getByTestId("catalog-check-reports").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-node-public").click()
  await picker.getByTestId("catalog-check-pipeline").click()
  await picker.getByTestId("card-picker-done").click()
  await expect(cards(page, database)).toContainText("pipeline")

  // Drawn with the mouse from a table to a folder: the panel says what it does.
  await drawLink(page, row(page, "pipeline"), row(page, "reports"))
  const panel = page.getByTestId("link-panel")
  await expect(panel.getByTestId("link-panel-sentence")).toHaveText(
    `Save as CSV: ${database} · pipeline → ${files} · reports`
  )
  await expect(panel.getByTestId("link-panel-result")).toHaveText("Not run yet")
  await panel.getByTestId("link-panel-name").fill(csv)

  // Run saves what is on the screen first, then runs what was saved.
  await panel.getByTestId("link-panel-run").click()
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("Done", { timeout: 20_000 })
  await expect(result).toContainText(`${csv} saved in reports`)
  await page.screenshot({ path: "test-results/pipelines-link.png" })

  // It stays, and runs again: the name is taken now, and the link says so.
  await panel.getByTestId("link-panel-run").click()
  await expect(result).toContainText("Failed", { timeout: 20_000 })
  await panel.getByTestId("link-panel-close").click()
  await expect(panel).toHaveCount(0)

  // The hint: what else could be drawn, dashed; pressed, one becomes a link.
  await page.getByTestId("pipeline-hint").click()
  const hinted = page.locator('[data-testid^="graph-edge-hint:"]')
  await expect(hinted.first()).toBeAttached()
  await expect(hinted.first()).toHaveAttribute("aria-label", "Save as CSV")
  await page.screenshot({ path: "test-results/pipelines-hint.png" })
  await hinted.first().press("Enter")
  await expect(panel.getByTestId("link-panel-sentence")).toHaveText(
    `Save as CSV: ${database} · pipeline → ${files} (top)`
  )
  await panel.getByTestId("link-panel-remove").click()
  await page.getByTestId("confirm-accept").click()
  await expect(panel).toHaveCount(0)

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})
