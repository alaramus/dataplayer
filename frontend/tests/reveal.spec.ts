import { expect, test } from "@playwright/test"

import { openNode } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { catalogTab, deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/**
 * Getting from the tab of a table back to the catalog it came from.
 *
 * In the browser because both halves are about the screen: which tab is in
 * front, and which row is marked in it.
 */

function rowsTabIcon(page: import("@playwright/test").Page) {
  return page.locator('[data-testid^="workspace-tab-icon-rows:"]').first()
}

test("names the table and not the connection, and says the connection in the tooltip", async ({
  page,
}) => {
  const name = `e2e-reveal-name-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "connector")

  const tab = rowsTabs(page).first()
  await expect(tab).toContainText("connector")
  // The column holds tables from several connections at once, so the name has
  // to be reachable — it moved into the tooltip, it did not go away.
  await expect(tab).not.toContainText(name)
  await rowsTabIcon(page).hover()
  await expect(page.getByText(`${name} · Show in catalog`)).toBeVisible()

  await deleteConnector(page, name)
})

test("brings the catalog forward and marks the row the table came from", async ({
  page,
}) => {
  const name = `e2e-reveal-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "connector")

  // Opening the table left the catalog behind in its own column; pressing the
  // icon of the data tab is the way back to it.
  await rowsTabIcon(page).click()

  await expect(catalogTab(page)).toHaveClass(/--active/)
  await expect(page.getByTestId("catalog-node-connector")).toHaveAttribute(
    "data-revealed",
    "true"
  )

  await deleteConnector(page, name)
})

test("opens the catalog again when it was closed", async ({ page }) => {
  const name = `e2e-reveal-closed-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "connector")

  await page.locator('[data-testid^="workspace-close-catalog:"]').first().click()
  await expect(page.locator('[data-testid^="workspace-tab-catalog:"]')).toHaveCount(0)

  await rowsTabIcon(page).click()

  await expect(page.locator('[data-testid^="workspace-tab-catalog:"]')).toHaveCount(1)
  await expect(page.getByTestId("catalog-node-connector")).toHaveAttribute(
    "data-revealed",
    "true"
  )

  await deleteConnector(page, name)
})
