import { expect, test } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import {
  createFileConnector,
  createPostgresConnector,
  openOptions,
} from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, editConnector, openConnector } from "./utils/workspace"

/**
 * Whether what is on screen was read or remembered, and the window that
 * decides it.
 *
 * In the browser because both halves are things a person has to see: a badge
 * computed and never rendered is the mistake this project has already made
 * once, and a window nobody can reach in the form is a column in a table
 * (D105).
 */

test("says whether a catalog level was read or kept, and reads it again when pressed", async ({
  page,
}) => {
  const name = `e2e-fresh-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  // The first reading of a level is a read of the source, whatever the
  // server does with it afterwards.
  const badge = page.getByTestId("catalog-freshness")
  await expect(badge).toBeVisible()
  await expect(badge).toHaveAttribute("data-live", "yes")

  const reread = page.waitForRequest((request) => request.url().includes("/catalog"))
  await badge.click()
  await reread
  await expect(badge).toBeVisible()

  await deleteConnector(page, name)
})

test("says how old a page of rows is, beside the rows", async ({ page }) => {
  const name = `e2e-fresh-rows-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "public")
  await openNode(page, "alembic_version")

  // Two badges on screen now, the level's and the grid's, and they are about
  // different readings.
  const badge = page.getByTestId("grid-freshness")
  await expect(badge).toBeVisible()
  await expect(badge).toContainText(/Live|\d+s/)

  await deleteConnector(page, name)
})

test("a connection is told how long to keep its answers", async ({ page }) => {
  const name = `e2e-fresh-window-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await editConnector(page, name)
  await openOptions(page)
  // What the connection does today, in durations rather than in a policy:
  // "as the source decides" says nothing to somebody who has not read the
  // driver (D105).
  await expect(page.getByTestId("connector-cache-window")).toContainText(
    "As this source decides (rows 10s, lists 30s)"
  )

  await page.getByTestId("connector-cache-window").click()
  await page.getByRole("option", { name: "Never keep answers", exact: true }).click()
  await page.getByTestId("save-connector").click()

  // Saved and read back: the window is on the connection, not on the form.
  await editConnector(page, name)
  await openOptions(page)
  await expect(page.getByTestId("connector-cache-window")).toContainText(
    "Never keep answers"
  )
  await page.locator('[data-testid^="window-close-connector"]').first().click()

  await deleteConnector(page, name)
})


test("says nothing about freshness over a source that is always read live", async ({
  page,
}) => {
  const name = `e2e-fresh-live-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await expect(page.getByTestId("catalog-list")).toBeVisible()

  // Personal storage never opted into caching, so there is nothing for a
  // badge to report and a permanent "Live" would read as a promise about a
  // cache that is not there (D105).
  await expect(page.getByTestId("catalog-freshness")).toHaveCount(0)

  await openNode(page, "reports")
  await expect(page.getByTestId("catalog-list")).toContainText("q3.csv")
  await expect(page.getByTestId("catalog-freshness")).toHaveCount(0)

  await deleteConnector(page, name)
})
