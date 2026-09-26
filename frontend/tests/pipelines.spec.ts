import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector } from "./utils/workspace"

/**
 * Pipelines (D175, D176, D177): connections dragged, or pressed, onto a
 * canvas become cards of what was ticked in them; rows are joined by links
 * that run as Paste does, the whole pipeline by one Run, link after link; the
 * pipeline is kept on the server.
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

test("joins two rows by a link, runs the pipeline from its head, and hints the others", async ({ page }) => {
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
  await expect(panel.getByTestId("link-panel-number")).toHaveText("1")
  await panel.getByTestId("link-panel-name").fill(csv)

  // The head's Run saves what is on the screen first, then runs what was saved.
  await page.getByTestId("pipeline-run").click()
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("Done", { timeout: 20_000 })
  await expect(result).toContainText(`${csv} saved in reports`)
  await expect(page.getByTestId("pipeline-last-run")).toContainText(`${csv} saved in reports`)
  const line = page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Save as CSV" })
  await expect(line).toHaveText("1 · Save as CSV")
  await page.screenshot({ path: "test-results/pipelines-link.png" })

  // It stays, and runs again: the name is taken now, and the link says so.
  await page.getByTestId("pipeline-run").click()
  await expect(result).toContainText("Failed", { timeout: 20_000 })
  await expect(page.getByTestId("pipeline-last-run")).toContainText("Stopped at 1 of 1, Save as CSV")
  await panel.getByTestId("link-panel-close").click()
  await expect(panel).toHaveCount(0)

  // The hint: what else could be drawn, dashed; pressed, one becomes a link.
  await page.getByTestId("pipeline-hint").click()
  // The file the runs made is a row of its card too (D178), and hinted from.
  const hinted = page.locator('[data-testid^="graph-edge-hint:"][aria-label="Save as CSV"]')
  await expect(hinted.first()).toBeAttached()
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

/** A row of the canvas by the node it names; the top of a connection names none. */
function port(page: Page, nodeId: string | null): Locator {
  const suffix = nodeId === null ? "-top" : `-node:${nodeId}`
  return page.getByTestId("pipeline-canvas").locator(`[data-testid^="graph-port-"][data-testid$="${suffix}"]`)
}

test("runs every link by one Run, stops at the first failure, and says where a circle was broken", async ({ page }) => {
  const stamp = Date.now()
  const database = `e2e-run-db-${stamp}`
  const files = `e2e-run-files-${stamp}`
  const csv = `e2e-run-${stamp}.csv`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)
  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()
  await expect(page.getByTestId("pipeline-run")).toBeDisabled()

  // A table on the left, and on its right the top of personal storage and a
  // folder in it.
  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-node-public").click()
  await picker.getByTestId("catalog-check-pipeline").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${files}`).click()
  await picker.getByTestId("card-picker-top").click()
  await picker.getByTestId("catalog-check-reports").click()
  await picker.getByTestId("card-picker-done").click()
  await expect(cards(page, files)).toContainText("reports")

  // The table saved as one name into both places: two links, run in the
  // order they were drawn, since they start from the same row.
  const panel = page.getByTestId("link-panel")
  await drawLink(page, port(page, "public.pipeline"), port(page, "reports"))
  await panel.getByTestId("link-panel-name").fill(csv)
  await panel.getByTestId("link-panel-close").click()
  await drawLink(page, port(page, "public.pipeline"), port(page, null))
  await panel.getByTestId("link-panel-name").fill(csv)
  const kept = saved(page)
  await panel.getByTestId("link-panel-close").click()
  await kept
  const labels = page.locator('[data-testid^="graph-edge-label-"]')
  await expect(labels).toHaveText(["1 · Save as CSV", "2 · Save as CSV"])

  // One Run, both links.
  const last = page.getByTestId("pipeline-last-run")
  await page.getByTestId("pipeline-run").click()
  await expect(last).toContainText("All 2 links ran", { timeout: 20_000 })
  await expect(page.locator('[data-tone="success"]')).toHaveCount(2)

  // Again: the first finds its name taken, and the second is not run.
  await page.getByTestId("pipeline-run").click()
  await expect(last).toContainText("Stopped at 1 of 2, Save as CSV", { timeout: 20_000 })
  await expect(last).toContainText("1 not run")
  await expect(page.locator('[data-tone="error"]')).toHaveCount(1)
  await expect(page.locator('[data-tone="muted"]')).toHaveCount(1)
  await labels.filter({ hasText: "2 · Save as CSV" }).click()
  await expect(panel.getByTestId("link-panel-result")).toHaveText("Not run: the run stopped before it")
  await page.screenshot({ path: "test-results/pipelines-run.png" })
  await panel.getByTestId("link-panel-close").click()

  // The file the first run left at the top, read into a new table beside the
  // table it came from: the two cards now write into each other.
  await page.getByTestId(`pipeline-card-settings-${files}`).click()
  await picker.getByTestId(`catalog-check-${csv}`).click()
  await picker.getByTestId("card-picker-done").click()
  await page.getByTestId(`pipeline-card-settings-${database}`).click()
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("card-picker-done").click()
  await drawLink(page, port(page, csv), port(page, "public"))
  await expect(panel.getByTestId("link-panel-sentence")).toContainText("Create a table")
  const drawn = saved(page)
  await panel.getByTestId("link-panel-close").click()
  await drawn
  await expect(labels.filter({ hasText: "Create a table" })).toHaveText("3 · Create a table")
  const broken = labels.filter({ hasText: "1 · Save as CSV" }).locator('[data-testid^="graph-edge-badge-"]')
  await broken.hover()
  await expect(page.getByText(`${database} and ${files} write into each other`)).toBeVisible()
  await page.screenshot({ path: "test-results/pipelines-circle.png" })

  // Its columns never chosen: nothing runs, and that link is opened.
  await page.getByTestId("pipeline-run").click()
  await expect(page.getByText("Nothing ran: 3 · Create a table needs its table named and its columns chosen")).toBeVisible()
  await expect(panel.getByTestId("link-panel-number")).toHaveText("3")

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("draws a chain before anything is made, runs it by one Run, and takes it apart with its maker", async ({ page }) => {
  const stamp = Date.now()
  const database = `e2e-chain-db-${stamp}`
  const files = `e2e-chain-files-${stamp}`
  const backup = `e2e-chain-backup-${stamp}`
  const csv = `e2e-chain-${stamp}.csv`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)
  await createFileConnector(page, backup)
  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()

  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-node-public").click()
  await picker.getByTestId("catalog-check-pipeline").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${files}`).click()
  await picker.getByTestId("catalog-check-reports").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${backup}`).click()
  await picker.getByTestId("card-picker-top").click()
  await picker.getByTestId("card-picker-done").click()
  await expect(cards(page, backup)).toHaveCount(1)
  // Three cards side by side: the first has been panned under the list.
  await page.getByTestId("pipeline-fit").click()

  // The table saved as CSV: the file it will make is a row of the folder's
  // card at once, before anything has run.
  const panel = page.getByTestId("link-panel")
  await drawLink(page, port(page, "public.pipeline"), port(page, "reports"))
  await panel.getByTestId("link-panel-name").fill(csv)
  const kept = saved(page)
  await panel.getByTestId("link-panel-close").click()
  await kept
  const result = cards(page, files).locator('[data-testid^="graph-port-"][data-testid*="-made:"]')
  await expect(result).toContainText(csv)
  await expect(result).toContainText("← 1")

  // And it is the source of the next link: copied to the other connection.
  await drawLink(page, result, cards(page, backup).locator('[data-testid^="graph-port-"][data-testid$="-top"]'))
  await expect(panel.getByTestId("link-panel-sentence")).toHaveText(
    `Copy files: ${files} · ${csv} → ${backup} (top)`
  )
  await panel.getByTestId("link-panel-close").click()
  await page.screenshot({ path: "test-results/pipelines-chain.png" })

  await page.getByTestId("pipeline-run").click()
  await expect(page.getByTestId("pipeline-last-run")).toContainText("All 2 links ran", { timeout: 20_000 })
  await page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Copy files" }).click()
  await expect(panel.getByTestId("link-panel-made")).toHaveText(`Read ${csv} · Made ${csv}`)

  // The link making the file taken away takes the copy with it, after saying so.
  await page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Save as CSV" }).click()
  await panel.getByTestId("link-panel-remove").click()
  await expect(page.getByTestId("confirm-message")).toContainText(`${backup} (top)`)
  await page.getByTestId("confirm-accept").click()
  await expect(page.locator('[data-testid^="graph-edge-label-"]')).toHaveCount(0)
  await expect(result).toHaveCount(0)

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, backup)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})
