import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

test("shows rows of a selected relation and pages through them", async ({ page }) => {
  const name = `e2e-rows-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await openConnector(page, name)
  // pg_catalog is used rather than an application table: it always holds
  // hundreds of rows, so paging is real rather than vacuous.
  await pickSchema(page, "pg_catalog")
  // Opening a relation puts it in a tab of its own.
  await openNode(page, "pg_class")
  await expect(rowsTabs(page)).toHaveCount(1)

  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("relname")
  await expect(grid.locator("tbody tr")).toHaveCount(50)
  await expect(grid).toContainText("Rows 1–50")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 51–100")

  await page.getByTestId("grid-prev").click()
  await expect(grid).toContainText("Rows 1–50")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
