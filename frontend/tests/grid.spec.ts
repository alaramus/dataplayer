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
  if ((await budget.textContent()) === "∅") {
    await budget.dblclick()
    await page.getByTestId("grid-edit-null").click()
    await page.getByTestId("grid-edit-value").fill("90000.00")
    await page.getByTestId("grid-edit-save").click()
    await expect(budget).toHaveText("90000.00")
  }

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("∅")

  await budget.dblclick()
  await page.getByTestId("grid-edit-null").click()
  await page.getByTestId("grid-edit-value").fill("90000.00")
  await page.getByTestId("grid-edit-save").click()
  await expect(budget).toHaveText("90000.00")

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
  await expect(page.getByTestId("grid-filter-command")).toHaveAttribute(
    "title",
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
