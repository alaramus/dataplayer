import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { nodeHeader } from "./utils/tree"
import { connectorAction, connectorRow, openConnector, rowsTabs } from "./utils/workspace"

test("shows rows of a selected relation and pages through them", async ({ page }) => {
  const name = `e2e-rows-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await openConnector(page, name)
  // pg_catalog is used rather than an application table: it always holds
  // hundreds of rows, so paging is real rather than vacuous.
  await nodeHeader(page, "pg_catalog").locator(".q-tree__arrow").click()
  // Selecting a relation opens it in a tab of its own.
  await nodeHeader(page, "pg_class").click()
  await expect(rowsTabs(page)).toHaveCount(1)

  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("relname")
  await expect(grid.locator("tbody tr")).toHaveCount(50)
  await expect(grid).toContainText("Rows 1–50")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 51–100")

  await page.getByTestId("grid-prev").click()
  await expect(grid).toContainText("Rows 1–50")

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})
