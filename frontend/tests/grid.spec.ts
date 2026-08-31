import { expect, test } from "@playwright/test"

import {
  addFilter,
  openNode,
  pickSchema,
  pinColumn,
  resizeColumn,
  selectRange,
  sortColumn,
} from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test("explores a relation and restores its view", async ({ page, context }) => {
  const name = `e2e-grid-${Date.now()}`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "status", "equals", "active")
  await addFilter(page, "budget", "greater than", "1000")
  await sortColumn(page, "priority")
  await sortColumn(page, "name", true)
  await expect(page.getByTestId("grid-sort-priority-name")).toHaveText("2")

  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "250", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await page.getByRole("checkbox", { name: "priority", exact: true }).click()
  await page.getByRole("checkbox", { name: "status", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await selectRange(page, "name", 0, "budget", 0)
  await page.getByTestId("grid-copy").click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(
    "Core Platform\t180000.00"
  )

  await resizeColumn(page, "name", 60)
  await pinColumn(page, "name")
  await page.reload()
  await expect(page.getByTestId("grid-column-name")).toHaveCSS("position", "sticky")
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1")
  await page.screenshot({ path: "test-results/grid-desktop.png", fullPage: true })

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("streams every matching row into a CSV download", async ({ page }) => {
  const name = `e2e-grid-export-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "status", "equals", "active")
  await page.getByTestId("grid-columns").click()
  await page.getByRole("checkbox", { name: "priority", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await page.getByTestId("grid-download").click()
  await expect(page.getByTestId("grid-download-dialog")).toContainText(
    "1 active filters"
  )
  await page.getByTestId("download-scope-all").click()

  const started = page.waitForEvent("download")
  await page.getByTestId("grid-download-run").click()
  const download = await started

  expect(download.suggestedFilename()).toMatch(/^projects-.*\.csv$/)
  await expect(
    page.locator(".q-notification", { hasText: "rows exported" })
  ).toBeVisible()

  await deleteConnector(page, name)
})

test("recovers from a rejected query without restoring it", async ({ page }) => {
  test.setTimeout(60_000)
  const name = `e2e-grid-query-error-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()

  await page.route("**/*", async (route) => {
    const request = route.request()
    if (request.method() !== "POST" || !request.url().includes("/fetch")) {
      await route.continue()
      return
    }
    const body = request.postDataJSON() as { filters?: unknown[] }
    if ((body.filters?.length ?? 0) === 0) {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Query failed" }),
    })
  })

  const applyRejectedFilter = async () => {
    const editor = page.getByTestId("grid-filter-editor")
    if (!(await editor.isVisible())) await page.getByTestId("grid-filter").click()
    await editor.getByLabel("Column").click()
    await page.getByRole("option", { name: "name", exact: true }).click()
    await editor.getByLabel("Operator").click()
    await page.getByRole("option", { name: "equals", exact: true }).click()
    await editor.getByLabel("Value").fill("rejected")
    await editor.getByTestId("grid-filter-apply").click()
    await expect(page.getByTestId("grid-error")).toContainText("Could not read the rows", {
      timeout: 15_000,
    })
  }

  await applyRejectedFilter()
  await page.getByTestId("grid-reset-query").click()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()

  await applyRejectedFilter()
  await page.reload()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await expect(page.getByTestId("grid-error")).toHaveCount(0)

  await deleteConnector(page, name)
})

test("opens a complete JSON value", async ({ page }) => {
  const name = `e2e-grid-json-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "audit_events")

  await page.getByTestId("grid-cell-0-payload").dblclick()
  await expect(page.getByTestId("grid-viewer")).toContainText('"source"')
  await expect(page.getByTestId("grid-viewer")).toContainText('"success"')
  await expect
    .poll(async () => (await page.getByTestId("grid-viewer").boundingBox())?.width ?? 0)
    .toBeGreaterThan(800)
  await page.screenshot({ path: "test-results/grid-dialog.png", fullPage: true })
  await page.getByRole("button", { name: "Close", exact: true }).click()
  await expect(page.getByTestId("grid-viewer")).toHaveCount(0)

  await deleteConnector(page, name)
})

test("edits one PostgreSQL cell and can write SQL NULL", async ({ page }) => {
  const name = `e2e-grid-edit-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await addFilter(page, "name", "equals", "Signal Research")
  const budget = page.getByTestId("grid-cell-0-budget")
  if ((await budget.textContent()) === "null") {
    await budget.dblclick()
    await page.getByTestId("grid-edit-null").click()
    await page.getByTestId("grid-edit-value").fill("90000.00")
    await page.getByTestId("grid-edit-save").click()
    await expect(budget).toHaveText("90000.00")
  }

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("null")

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-value").fill("90000.00")
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("90000.00")

  await deleteConnector(page, name)
})

test("inserts and deletes a PostgreSQL row", async ({ page }) => {
  const name = `e2e-grid-mutations-${Date.now()}`
  const label = `e2e-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "equals", label, false)
  await expect(page.getByTestId("grid-empty")).toBeVisible()
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-save").click()

  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)
  await expect(page.getByTestId("grid-cell-0-color")).toHaveText("#64748B")
  await page.getByTestId("grid-select-row-0").click()
  await expect(page.getByTestId("grid-delete")).toBeEnabled()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("states that a CSV cannot be filtered or sorted", async ({ page }) => {
  const name = `e2e-grid-csv-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "sample.csv")

  await expect(page.getByTestId("grid-filter")).toBeDisabled()
  await expect(page.getByTestId("grid-sort")).toBeDisabled()
  await page.getByTestId("grid-filter-command").hover()
  await expect(page.locator(".app-tooltip")).toHaveCount(1)
  await expect(page.locator(".app-tooltip")).toHaveText(
    "This source does not support filtering"
  )

  await deleteConnector(page, name)
})

test("keeps the grid legible in the dark theme", async ({ page }) => {
  const name = `e2e-grid-dark-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  await page.getByTestId("theme-toggle").click()
  await expect(page.locator("body.body--dark")).toHaveCount(1)
  await expect(page.getByTestId("grid-header")).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await page.screenshot({ path: "test-results/grid-dark.png", fullPage: true })

  await deleteConnector(page, name)
})

test("keeps a narrow grid header, rows and pager separate", async ({ page }) => {
  const name = `e2e-grid-narrow-${Date.now()}`
  await page.setViewportSize({ width: 900, height: 720 })
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")

  const header = await page.getByTestId("grid-header").boundingBox()
  const cell = await page.getByTestId("grid-cell-0-name").boundingBox()
  const pager = await page.getByTestId("grid-page-range").boundingBox()
  if (header === null || cell === null || pager === null) throw new Error("the grid is not laid out")
  expect(header.y + header.height).toBeLessThanOrEqual(cell.y)
  expect(cell.y + cell.height).toBeLessThanOrEqual(pager.y)
  await page.screenshot({ path: "test-results/grid-narrow.png", fullPage: true })

  await deleteConnector(page, name)
})

test("keeps the 500-row page mode interactive", async ({ page, context }) => {
  const name = `e2e-grid-500-${Date.now()}`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")

  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "500", exact: true }).click()
  await page.getByTestId("grid-cell-0-relname").click()
  await page.getByTestId("grid-copy").click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).not.toBe("")
  await sortColumn(page, "relname")
  await expect(page.getByTestId("grid-sort-direction-relname")).toBeVisible()
  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "50", exact: true }).click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1–50")

  await page.getByTestId("grid-next").click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 51–100")

  await page.getByTestId("grid-prev").click()
  await expect(page.getByTestId("grid-page-range")).toContainText("Rows 1–50")

  await deleteConnector(page, name)
})

test("pastes a block of cells and refuses one the column cannot read", async ({
  page,
  context,
}) => {
  const name = `e2e-grid-paste-${Date.now()}`
  const label = `e2e-paste-${Date.now()}`
  const pasted = `${label}-done`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "contains", label, false)
  await expect(page.getByTestId("grid-empty")).toBeVisible()
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-save").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)

  // Two cells at once, landing from the selected one: the block is the app's
  // own TSV, and nothing about it is typed into a form.
  await page.evaluate(
    (text) => navigator.clipboard.writeText(text),
    `${pasted}\t#123456`
  )
  await page.getByTestId("grid-cell-0-label").click()
  await page.getByTestId("grid-paste").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(pasted)
  await expect(page.getByTestId("grid-cell-0-color")).toHaveText("#123456")

  // A value the column's type cannot read is named, and nothing is written.
  await page.evaluate(() => navigator.clipboard.writeText("not a number"))
  await page.getByTestId("grid-cell-0-organization_id").click()
  await page.getByTestId("grid-paste").click()
  await expect(page.locator(".q-notification", { hasText: "cannot be read" })).toBeVisible()
  // Contains rather than equals: a foreign-key cell also carries the arrow
  // that leads to the row it names.
  const key = page.getByTestId("grid-cell-0-organization_id")
  await expect(key).not.toContainText("not a number")
  await expect(key).toContainText("1")

  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("keeps a row in its place when one of its cells is edited", async ({ page }) => {
  const name = `e2e-grid-order-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "app_users")

  // Two rows are enough to tell an order from an accident.
  const first = await page.getByTestId("grid-cell-0-email").textContent()
  const second = await page.getByTestId("grid-cell-1-email").textContent()
  expect(first).not.toBe(second)

  const cell = page.getByTestId("grid-cell-0-full_name")
  const before = (await cell.textContent()) ?? ""
  await cell.dblclick()
  await page.getByTestId("grid-edit-value").fill(`${before} edited`)
  await page.getByTestId("grid-edit-save").click()
  await expect(cell).toHaveText(`${before} edited`)

  // PostgreSQL wrote the changed row somewhere else in the heap; the page is
  // ordered by the key, so the reader does not see it move (D42).
  await expect(page.getByTestId("grid-cell-0-email")).toHaveText(first ?? "")
  await expect(page.getByTestId("grid-cell-1-email")).toHaveText(second ?? "")

  await cell.dblclick()
  await page.getByTestId("grid-edit-value").fill(before)
  await page.getByTestId("grid-edit-save").click()
  await expect(cell).toHaveText(before)

  await deleteConnector(page, name)
})

test("copies a whole row and fills a new one from it", async ({ page, context }) => {
  const name = `e2e-grid-duplicate-${Date.now()}`
  const label = `e2e-dup-${Date.now()}`
  const copy = `${label}-copy`
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  // One row of our own to copy, so nothing in the fixture is duplicated.
  await addFilter(page, "label", "contains", label, false)
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-value-organization_id").fill("1")
  await page.getByTestId("grid-insert-value-label").fill(label)
  await page.getByTestId("grid-insert-value-color").fill("#ABCDEF")
  await page.getByTestId("grid-insert-save").click()
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText(label)

  // Select the whole row and copy it.
  await page.getByTestId("grid-cell-0-tag_id").click()
  await page.getByTestId("grid-cell-0-color").click({ modifiers: ["Shift"] })
  await page.getByTestId("grid-copy").click()

  // A new row filled from that line: the identity is the source's, so it is
  // named as left out rather than dictated.
  await page.getByTestId("grid-insert").click()
  await page.getByTestId("grid-insert-paste").click()
  await expect(
    page.locator(".q-notification", { hasText: "Left to the source: tag_id" })
  ).toBeVisible()
  await expect(page.getByTestId("grid-insert-value-color")).toHaveValue("#ABCDEF")
  await page.getByTestId("grid-insert-value-label").fill(copy)
  await page.getByTestId("grid-insert-save").click()

  await expect(page.getByTestId("grid-cell-1-label")).toHaveText(copy)
  await expect(page.getByTestId("grid-cell-1-color")).toHaveText("#ABCDEF")

  // One at a time: ticking a row replaces the selection rather than adding to it.
  for (let left = 2; left > 0; left -= 1) {
    await page.getByTestId("grid-select-row-0").click()
    await page.getByTestId("grid-delete").click()
    await page.getByTestId("confirm-accept").click()
    // The page has to be re-read before row 0 is ticked again. Without this
    // the second tick lands on the row still being deleted, and the source
    // correctly refuses to delete it twice.
    await expect(page.getByTestId("row-grid").locator("tbody tr")).toHaveCount(
      left - 1
    )
  }
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("brings rows in from a file in personal storage", async ({ page }) => {
  const target = `e2e-import-target-${Date.now()}`
  const source = `e2e-import-source-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, target)
  await createFileConnector(page, source)
  await openConnector(page, target)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  // Nothing of ours is there yet. By label, because the two the file carries
  // are named uniquely enough that a test running beside this one cannot make
  // them appear.
  await addFilter(page, "label", "equals", "one", false)

  await page.getByTestId("grid-import").click()
  await page.getByTestId("grid-import-source").click()
  await page.getByRole("option", { name: source, exact: true }).click()
  await page.getByTestId("grid-import-node-sample.tsv").click()

  // The file's own columns, paired by hand: nothing is matched silently.
  // Every pair offers the same source columns, so a menu still closing from
  // the previous one would swallow the click. Wait for exactly one list.
  const lists = page.getByRole("listbox")
  const pair = async (target: string, source: string) => {
    await expect(lists).toHaveCount(0)
    await page.getByTestId(`grid-import-pair-${target}`).click()
    await expect(lists).toHaveCount(1)
    await page.getByRole("option", { name: source, exact: true }).click()
    await expect(page.getByTestId(`grid-import-pair-${target}`)).toContainText(source)
  }
  await pair("organization_id", "id")
  await pair("label", "name")

  await page.getByTestId("grid-import-preview").click()
  await expect(page.getByTestId("grid-import-dialog")).toContainText("one")

  await page.getByTestId("grid-import-run").click()
  await expect(
    page.locator(".q-notification", { hasText: "2 rows brought in" })
  ).toBeVisible()

  // The first of them, through the filter that showed nothing a moment ago.
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText("one")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  // And the second, which proves both arrived.
  await page.getByTestId("grid-filter-clear").click()
  await addFilter(page, "label", "equals", "two")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, target)
  await deleteConnector(page, source)
})

test("brings rows in from a table through another database connection", async ({ page }) => {
  const target = `e2e-table-import-target-${Date.now()}`
  const source = `e2e-table-import-source-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, target)
  await createPostgresConnector(page, source)
  await openConnector(page, target)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")

  await addFilter(page, "label", "equals", "Northstar Labs", false)
  await page.getByTestId("grid-import").click()
  await page.getByTestId("grid-import-source").click()
  await page.getByRole("option", { name: source, exact: true }).click()
  await page.getByTestId("grid-import-node-demo_lab").click()
  await page.getByTestId("grid-import-node-organizations").click()

  const lists = page.getByRole("listbox")
  const pair = async (targetColumn: string, sourceColumn: string) => {
    await expect(lists).toHaveCount(0)
    await page.getByTestId(`grid-import-pair-${targetColumn}`).click()
    await expect(lists).toHaveCount(1)
    await page.getByRole("option", { name: sourceColumn, exact: true }).click()
    await expect(page.getByTestId(`grid-import-pair-${targetColumn}`)).toContainText(
      sourceColumn
    )
  }
  await pair("organization_id", "organization_id")
  await pair("label", "display_name")

  await page.getByTestId("grid-import-preview").click()
  await expect(page.getByTestId("grid-import-dialog")).toContainText("Northstar Labs")
  await page.getByTestId("grid-import-run").click()
  await expect(
    page.locator(".q-notification", { hasText: "2 rows brought in" })
  ).toBeVisible()

  await expect(page.getByTestId("grid-cell-0-label")).toHaveText("Northstar Labs")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await page.getByTestId("grid-filter-clear").click()
  await addFilter(page, "label", "equals", "Blue Orbit")
  await page.getByTestId("grid-select-row-0").click()
  await page.getByTestId("grid-delete").click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("grid-empty")).toBeVisible()

  await deleteConnector(page, target)
  await deleteConnector(page, source)
})
