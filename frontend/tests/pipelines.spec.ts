import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { canvasRow, drawLink, runOnce, openSchedule, pipelineMenu } from "./utils/pipelines"
import { deleteConnector } from "./utils/workspace"

/**
 * Pipelines (D175, D176, D177): connections dragged, or pressed, onto a
 * canvas become cards of what was ticked in them; rows are joined by links
 * that run as Paste does, the whole pipeline by one Run, link after link; the
 * pipeline is kept on the server, and so are its runs (D180).
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
  await pipelineMenu(page, "rename")
  await page.getByTestId("pipeline-rename-input").fill(name)
  const renamed = saved(page)
  // Enter closes the window; it once reopened it through the pencil.
  await page.getByTestId("pipeline-rename-input").press("Enter")
  await renamed
  await expect(page.getByRole("dialog", { name: "Rename pipeline" })).toHaveCount(0)
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

  await pipelineMenu(page, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("pipeline-view").or(page.getByTestId("pipeline-create-first"))).toBeVisible()
  await expect(page.getByTestId("pipelines-space")).not.toContainText(name)

  await page.getByTestId("space-data").click()
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})



test("joins two rows by a link, runs it once from the head's menu, and tints where a drag can go", async ({ page }) => {
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
  await drawLink(page, canvasRow(page, "pipeline"), canvasRow(page, "reports"))
  const panel = page.getByTestId("link-panel")
  await expect(panel.getByTestId("link-panel-sentence")).toHaveText(
    `Save as CSV: ${database} · pipeline → ${files} · reports`
  )
  await expect(panel.getByTestId("link-panel-result")).toHaveText("Not run yet")
  await expect(panel.getByTestId("link-panel-number")).toHaveText("1")
  await panel.getByTestId("link-panel-name").fill(csv)

  // Run once saves what is on the screen first, then runs what was saved.
  await runOnce(page)
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("Done", { timeout: 20_000 })
  await expect(result).toContainText(`${csv} saved in reports`)
  const line = page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Save as CSV" })
  await expect(line).toHaveText("1 · Save as CSV")
  await page.screenshot({ path: "test-results/pipelines-link.png" })

  // It stays, and runs again: the name is taken now, and the link says so.
  await runOnce(page)
  await expect(result).toContainText("Failed", { timeout: 20_000 })
  await panel.getByTestId("link-panel-close").click()
  await expect(panel).toHaveCount(0)

  // A drag tints the rows it can go to with what a drop draws (D363); the row
  // it is already linked to says so, faded.
  const table = await canvasRow(page, "pipeline").boundingBox()
  const top = cards(page, files).locator('[data-testid^="graph-port-"][data-testid$="-top"]')
  const reports = canvasRow(page, "reports")
  if (table === null) throw new Error("The table's row is not on screen")
  await page.mouse.move(table.x + table.width / 2, table.y + table.height / 2)
  await page.mouse.down()
  await page.mouse.move(table.x + table.width / 2 + 40, table.y + table.height / 2 + 10, { steps: 6 })
  await expect(top).toHaveClass(/graph-node__row--fit/)
  await expect(top).toContainText("Save as CSV")
  await expect(reports).toHaveClass(/graph-node__row--unfit/)
  await expect(reports).toContainText("Already linked")
  await page.screenshot({ path: "test-results/pipelines-drag.png" })
  const spot = await top.boundingBox()
  if (spot === null) throw new Error("The top's row is not on screen")
  await page.mouse.move(spot.x + spot.width / 2, spot.y + spot.height / 2, { steps: 6 })
  await page.mouse.up()
  await expect(panel.getByTestId("link-panel-sentence")).toHaveText(
    `Save as CSV: ${database} · pipeline → ${files} (top)`
  )
  // Neutral at rest and red under the pointer, as every destructive command in
  // a row is (D186).
  await expect(panel.getByTestId("link-panel-remove")).toHaveClass(/app-icon-button--danger/)
  await panel.getByTestId("link-panel-remove").click()
  await page.getByTestId("confirm-accept").click()
  await expect(panel).toHaveCount(0)

  await pipelineMenu(page, "delete")
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
  // Nothing drawn: Run once is off, and the status line says how to start.
  await page.getByTestId("pipeline-run-menu").click()
  await expect(page.getByTestId("menu-item-run-once")).toHaveAttribute("aria-disabled", "true")
  await page.keyboard.press("Escape")

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
  await runOnce(page)
  await expect(page.locator('[data-tone="success"]')).toHaveCount(2, { timeout: 20_000 })

  // Again: the first finds its name taken, and the second is not run.
  await runOnce(page)
  await expect(page.locator('[data-tone="error"]')).toHaveCount(1, { timeout: 20_000 })
  await expect(page.locator('[data-tone="muted"]')).toHaveCount(1)
  await labels.filter({ hasText: "2 · Save as CSV" }).click()
  await expect(panel.getByTestId("link-panel-result")).toHaveText("Not run: the run stopped before it")
  await page.screenshot({ path: "test-results/pipelines-run.png" })

  // The failure is said on screen at once, and is one entry, in Needs you —
  // not also a row left in Working or a message in Recent (D181).
  await expect(page.getByTestId("toast").filter({ hasText: "could not be completed" })).toBeVisible({ timeout: 20_000 })
  await page.getByTestId("activity-indicator").click()
  const sheet = page.getByTestId("activity-panel")
  await expect(sheet.getByTestId("attention-section")).toContainText("Stopped at 1 of 2, Save as CSV")
  await expect(sheet.getByTestId("working-section")).toContainText("Nothing is running")
  await expect(sheet.getByTestId("recent-section")).not.toContainText("Stopped at 1 of 2")
  await page.keyboard.press("Escape")

  // The history (D180): both runs, newest first, by hand, each with its
  // sentence; the canvas shows the newest.
  await pipelineMenu(page, "history")
  const history = page.getByTestId("history-window")
  const runs = history.getByTestId("history-run")
  await expect(runs).toHaveCount(2)
  await expect(runs.nth(0)).toContainText("Stopped at 1 of 2, Save as CSV")
  await expect(runs.nth(0)).toContainText("1 not run")
  await expect(runs.nth(0)).toContainText("by hand · took")
  await expect(runs.nth(0)).toHaveAttribute("aria-pressed", "true")
  await expect(runs.nth(1)).toContainText("All 2 links ran")
  await page.screenshot({ path: "test-results/pipelines-history.png" })

  // The older one pressed: the lines and the panel say what it did then.
  await runs.nth(1).click()
  await expect(runs.nth(1)).toHaveAttribute("aria-pressed", "true")
  await page.locator('[data-testid^="window-close-dialog:history-window"]').click()
  await expect(history).toHaveCount(0)
  await expect(page.getByTestId("pipeline-shown-run")).toContainText("Showing the run of")
  await expect(page.locator('[data-tone="success"]')).toHaveCount(2)
  await expect(panel.getByTestId("link-panel-result")).toContainText("Done")
  await page.screenshot({ path: "test-results/pipelines-history-shown.png" })

  // And back: the last run's colours again.
  await page.getByTestId("pipeline-shown-run-back").click()
  await expect(page.getByTestId("pipeline-shown-run")).toHaveCount(0)
  await expect(page.locator('[data-tone="error"]')).toHaveCount(1)
  await expect(panel.getByTestId("link-panel-result")).toHaveText("Not run: the run stopped before it")

  // Shown again, then Run: the canvas follows the run it starts.
  await pipelineMenu(page, "history")
  await runs.nth(1).click()
  await page.locator('[data-testid^="window-close-dialog:history-window"]').click()
  await expect(page.getByTestId("pipeline-shown-run")).toBeVisible()
  await runOnce(page)
  await expect(page.getByTestId("pipeline-shown-run")).toHaveCount(0)
  await expect(page.locator('[data-tone="error"]')).toHaveCount(1, { timeout: 20_000 })
  await panel.getByTestId("link-panel-close").click()

  // The file the first run left at the top, read into a new table beside the
  // table it came from: the two cards now write into each other.
  await page.getByTestId(`pipeline-card-settings-${files}`).click()
  await picker.getByTestId(`catalog-check-${csv}`).click()
  await picker.getByTestId("card-picker-done").click()
  await page.getByTestId(`pipeline-card-settings-${database}`).click()
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("card-picker-done").click()
  const drawn = saved(page)
  await drawLink(page, port(page, csv), port(page, "public"))
  await expect(panel.getByTestId("link-panel-sentence")).toContainText("Create a table")
  // Drawn ready (D364): named after the file it is read from, with all its
  // columns, and no window to press through.
  await drawn
  await expect(page.getByTestId("grid-create-table-dialog")).toHaveCount(0)
  await expect(panel.getByTestId("link-panel-columns")).toContainText(csv.replace(/\.csv$/, "").replaceAll("-", "_"))
  await panel.getByTestId("link-panel-close").click()
  await expect(labels.filter({ hasText: "Create a table" })).toHaveText("3 · Create a table")
  const broken = labels.filter({ hasText: "1 · Save as CSV" }).locator('[data-testid^="graph-edge-badge-"]')
  await broken.hover()
  await expect(page.getByText(`${database} and ${files} write into each other`)).toBeVisible()
  await page.screenshot({ path: "test-results/pipelines-circle.png" })

  await pipelineMenu(page, "delete")
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
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/pipelines") && response.request().method() === "POST"
  )
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await created
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

  await runOnce(page)
  await expect(page.locator('[data-tone="success"]')).toHaveCount(2, { timeout: 20_000 })
  await page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Copy files" }).click()
  await expect(panel.getByTestId("link-panel-made")).toHaveText(`Read ${csv} · Made ${csv}`)

  // The link making the file taken away takes the copy with it, after saying so.
  await page.locator('[data-testid^="graph-edge-label-"]', { hasText: "Save as CSV" }).click()
  await panel.getByTestId("link-panel-remove").click()
  await expect(page.getByTestId("confirm-message")).toContainText(`${backup} (top)`)
  await page.getByTestId("confirm-accept").click()
  await expect(page.locator('[data-testid^="graph-edge-label-"]')).toHaveCount(0)
  await expect(result).toHaveCount(0)

  await pipelineMenu(page, "delete")
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, backup)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("runs its scheduled links only while switched on, says when next, and asks for a schedule first", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-pipelines").click()
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/pipelines") && response.request().method() === "POST"
  )
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await created
  // A link to run on the schedule: a table saved as CSV into the top of storage.
  const files = `e2e-sched-files-${Date.now()}`
  const database = `e2e-sched-db-${Date.now()}`
  await page.getByTestId("space-data").click()
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)
  await page.getByTestId("space-pipelines").click()
  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-node-public").click()
  await picker.getByTestId("catalog-check-pipeline").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${files}`).click()
  await picker.getByTestId("card-picker-top").click()
  await picker.getByTestId("card-picker-done").click()
  const drawn = page.waitForResponse(
    (response) => /\/api\/v1\/pipelines\/[^/]+$/.test(response.url()) && response.request().method() === "PUT"
  )
  // Placed beside the first, the view pans to show it: let it settle.
  await expect(port(page, null)).toBeInViewport()
  await page.getByTestId("pipeline-fit").click()
  await drawLink(page, port(page, "public.pipeline"), port(page, null))
  await drawn
  await page.getByTestId("link-panel").getByTestId("link-panel-close").click()

  // A scheduled link and no schedule: the status line asks for one, and
  // Switch on refuses and opens the schedule's window.
  const status = page.getByTestId("pipeline-status")
  await expect(status).toHaveAttribute("data-kind", "no_schedule")
  await expect(status).toContainText("1 link runs on the schedule, and no schedule is set")
  const window = page.getByTestId("schedule-window")
  await page.getByTestId("pipeline-switch").click()
  await expect(window).toBeVisible()

  // Every night at 03:00, in this browser's clock.
  const kept = () => page.waitForResponse(
    (response) => response.url().endsWith("/schedule") && response.request().method() === "PUT"
  )
  await expect(window.getByTestId("schedule-time-0")).toHaveValue("03:00")
  await page.screenshot({ path: "test-results/pipelines-schedule-window.png" })
  let saved = kept()
  await window.getByTestId("schedule-save").click()
  await saved
  await expect(window).toHaveCount(0)
  await expect(status).toHaveAttribute("data-kind", "ready")

  // On: the line says when it runs next.
  await page.getByTestId("pipeline-switch").click()
  await expect(page.getByTestId("pipeline-switch")).toContainText("Switch off")
  await expect(status).toContainText(/next run (today|tomorrow) 03:00/)
  await page.screenshot({ path: "test-results/pipelines-schedule.png" })

  // Every hour instead: the next time is within the hour.
  await openSchedule(page)
  await window.getByTestId("schedule-kind-interval").click()
  await expect(window.getByTestId("schedule-every")).toHaveValue("1")
  saved = kept()
  await window.getByTestId("schedule-save").click()
  await saved
  await expect(status).toContainText(/next run (today|tomorrow) \d\d:\d\d/)

  // Off: nothing runs by itself, and the choice is kept for next time.
  await page.getByTestId("pipeline-switch").click()
  await expect(page.getByTestId("pipeline-switch")).toContainText("Switch on")
  await expect(status).toHaveAttribute("data-kind", "ready")
  await openSchedule(page)
  await expect(window.getByTestId("schedule-every")).toHaveValue("1")
  await window.getByRole("button", { name: "Cancel" }).click()

  await pipelineMenu(page, "delete")
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("keeps the head of the connections in place from Data to Pipelines, both at their narrowest", async ({ page }) => {
  const name = `e2e-pipe-head-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  async function narrowest(separator: Locator) {
    const box = await separator.boundingBox()
    if (box === null) throw new Error("the separator has no box")
    const y = box.y + box.height / 2
    await page.mouse.move(box.x + box.width / 2, y)
    await page.mouse.down()
    await page.mouse.move(20, y, { steps: 10 })
    await page.mouse.up()
  }
  function places(card: Locator) {
    return card.getByTestId("connectors-head").getByRole("button").evaluateAll((buttons) =>
      buttons.map((button) => {
        const box = button.getBoundingClientRect()
        return { x: box.x, y: box.y }
      })
    )
  }

  const data = page.getByTestId("workspace-leaf-sources")
  await narrowest(page.getByTestId("workspace-separator").first())
  const inData = await places(data)
  const dataWidth = (await data.boundingBox())?.width ?? 0

  await page.getByTestId("space-pipelines").click()
  const rail = page.getByTestId("pipelines-rail")
  await expect(rail).toBeVisible()
  await narrowest(page.getByTestId("pipelines-space").getByTestId("workspace-separator"))
  const inPipelines = await places(rail)

  // The same card at the same width, and every button of its head where it
  // was. The column in Data carried an empty box of commands, whose gap alone
  // moved the three buttons two pixels to the left.
  expect(Math.abs(((await rail.boundingBox())?.width ?? 0) - dataWidth)).toBeLessThan(0.5)
  expect(inData).toHaveLength(3)
  expect(inPipelines).toHaveLength(inData.length)
  inData.forEach((place, index) => {
    const other = inPipelines[index]
    expect(Math.abs((other?.x ?? 0) - place.x)).toBeLessThan(0.5)
    expect(Math.abs((other?.y ?? 0) - place.y)).toBeLessThan(0.5)
  })

  await page.getByTestId("space-data").click()
  await deleteConnector(page, name)
})
