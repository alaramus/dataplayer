import { expect, test } from "@playwright/test"

import { openNode } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

/**
 * Re-reading a panel from its own row of commands.
 *
 * The button used to sit on the tab and now sits with everything else the
 * panel offers (D112), so each of these presses it where a panel draws it —
 * which also means only the panel on screen has one.
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
  await page.getByTestId("catalog-panel").getByTestId("panel-reload").click()
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
  await page.getByTestId("connectors-panel").getByTestId("panel-reload").click()
  await reread

  await expect(page.getByTestId(`connector-${name}`)).toBeVisible()
  // Pressing reload is not opening: no catalog was asked for.
  await expect(page.locator('[data-testid^="workspace-tab-catalog:"]')).toHaveCount(0)

  await deleteConnector(page, name)
})

test("re-reads the page a table is showing, from the row of commands above it", async ({
  page,
}) => {
  const name = `e2e-reload-rows-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await openNode(page, "sample.csv")
  await expect(page.getByTestId("grid-header")).toBeVisible()

  const reread = page.waitForRequest(
    (request) => request.url().includes("/fetch") && request.method() === "POST"
  )
  await page.getByTestId("grid-header").getByTestId("panel-reload").click()
  await reread

  await expect(page.getByTestId("grid-header")).toBeVisible()

  await deleteConnector(page, name)
})
