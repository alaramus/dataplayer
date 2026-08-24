import { expect, test } from "@playwright/test"

import { openNode, showOnlySchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
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

  // And it takes itself off. Held any longer it would stop saying "here it is"
  // and start reading as a state the row is in.
  await expect(page.getByTestId("catalog-node-connector")).not.toHaveAttribute(
    "data-revealed",
    "true",
    { timeout: 10_000 }
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

test("comes back to the level the table lives on, whatever the catalog is showing", async ({
  page,
}) => {
  const name = `e2e-reveal-level-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await openNode(page, "connector")

  // The catalog is left showing a different schema, so the table is no longer
  // among the rows: without the path from the source there is nothing to mark.
  await showOnlySchema(page, "pg_catalog", "public")
  await expect(page.getByTestId("catalog-node-connector")).toHaveCount(0)

  await rowsTabIcon(page).click()

  await expect(page.getByTestId("catalog-node-connector")).toHaveAttribute(
    "data-revealed",
    "true"
  )

  await deleteConnector(page, name)
})

test("walks into the directory a file lives in", async ({ page }) => {
  const name = `e2e-reveal-file-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await openNode(page, "reports")
  await openNode(page, "q3.csv")

  // Back to the top of the source: the file is a level below and cannot be
  // marked where we are standing.
  await page.getByTestId("catalog-home").click()
  await expect(page.getByTestId("catalog-node-q3.csv")).toHaveCount(0)

  await rowsTabIcon(page).click()

  await expect(page.getByTestId("catalog-path")).toContainText("reports")
  await expect(page.getByTestId("catalog-node-q3.csv")).toHaveAttribute(
    "data-revealed",
    "true"
  )

  await deleteConnector(page, name)
})
