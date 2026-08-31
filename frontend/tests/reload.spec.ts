import { expect, test } from "@playwright/test"

import { openNode } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import {
  catalogTab,
  connectionsTab,
  deleteConnector,
  openConnector,
  rowsTabs,
} from "./utils/workspace"

/**
 * Re-reading a tab from its own strip.
 *
 * In the browser because the point is that the request goes out again and the
 * screen does not move: neither half can be shown by mounting a component.
 */

test("re-reads the level a catalog tab is standing on, and stays there", async ({
  page,
}) => {
  const name = `e2e-reload-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await openNode(page, "reports")
  await expect(page.getByTestId("catalog-path")).toContainText("reports")

  const reread = page.waitForRequest(
    (request) => request.url().includes("/catalog") && request.url().includes("reports")
  )
  await catalogTab(page).getByTestId(/^workspace-reload-catalog:/).click()
  await reread

  // Still inside the directory: the button says "read this again", not "start
  // over", so the path and the list are where they were.
  await expect(page.getByTestId("catalog-path")).toContainText("reports")
  await expect(page.getByTestId("catalog-list")).toContainText("q3.csv")

  await deleteConnector(page, name)
})

test("re-reads the list of connections without opening anything", async ({ page }) => {
  const name = `e2e-reload-list-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  const reread = page.waitForRequest(
    (request) =>
      request.url().includes("/api/v1/connectors/") && request.method() === "GET"
  )
  await connectionsTab(page).getByTestId("workspace-reload-connectors").click()
  await reread

  await expect(page.getByTestId(`connector-${name}`)).toBeVisible()
  // Pressing reload is not opening: no catalog was asked for.
  await expect(page.locator('[data-testid^="workspace-tab-catalog:"]')).toHaveCount(0)

  await deleteConnector(page, name)
})

test("a tab restored but never opened is read by showing it", async ({ page }) => {
  const name = `e2e-reload-cold-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await openNode(page, "sample.csv")
  await openNode(page, "notes.txt")
  // Two work tabs of different kinds: a CSV is rows, a text file is its own
  // source. Which one is cold after the reload is what this test is about.
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(page.locator('[data-testid^="workspace-tab-content:"]')).toHaveCount(1)

  // After a reload of the page only the active tab is mounted, so the other
  // one has registered no way of being re-read. Pressing its button has to do
  // something all the same, and reading a panel that never read anything is
  // showing it.
  await page.reload()
  const cold = page.locator('[data-testid^="workspace-tab-rows:"]').first()
  await expect(cold).not.toHaveClass(/--active/)

  await cold.getByTestId(/^workspace-reload-rows:/).click()

  await expect(cold).toHaveClass(/--active/)

  await deleteConnector(page, name)
})
