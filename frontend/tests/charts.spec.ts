import { expect, test } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

test("opens a bounded chart beside the current table page", async ({ page }) => {
  const name = `e2e-chart-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(page.getByTestId("grid-cell-0-budget")).toBeVisible()

  await page.getByTestId("grid-charts").click()
  await expect(page.getByTestId("chart-panel")).toBeVisible()
  await expect(page.getByTestId("chart-panel")).toContainText("Current page · Rows 1")
  await expect(page.getByTestId("chart-renderer")).toBeVisible()
  await expect(page.getByTestId("chart-type")).toBeVisible()
  await expect(page.locator('[data-testid="chart-renderer"] svg')).toBeVisible()

  await page.getByTestId("chart-type").click()
  await page.getByRole("option", { name: "Pie", exact: true }).click()
  await expect(page.getByTestId("chart-panel")).toContainText(
    "The chart uses only this bounded result"
  )

  await deleteConnector(page, name)
})

test("charts numeric text on one bounded CSV page without changing its source type", async ({
  page,
}) => {
  const name = `e2e-chart-file-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "sample.csv")
  await expect(page.getByTestId("grid-cell-0-population")).toBeVisible()

  await page.getByTestId("grid-charts").click()
  await expect(page.getByTestId("chart-renderer")).toBeVisible()
  await page.getByTestId("chart-measure").click()
  await page.getByRole("option", { name: "population (numeric on this page)", exact: true }).click()

  await deleteConnector(page, name)
})
