import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector } from "./utils/workspace"

/**
 * A query document, end to end.
 *
 * What no unit test can show: that the console is a panel of this workspace,
 * that a draft survives a reload because the server holds it, and that
 * deleting one is Trash rather than loss (D63, D65). There is no Run in this
 * slice — the document is the whole subject.
 */

async function openQueries(page: Page, connector: string) {
  await page.getByTestId("open-queries").click()
  await page.getByTestId("queries-connector").click()
  await page.getByRole("option", { name: connector, exact: true }).click()
}

async function typeQuery(page: Page, sql: string) {
  await page.locator(".cm-content").click()
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type(sql)
}

test("writes a query document, names it, and finds it again after a reload", async ({
  page,
}) => {
  const name = `e2e-query-${Date.now()}`
  // Named per run: the library is a person's whole library, and a document
  // left behind by an earlier run is exactly what a search must not confuse
  // this one with.
  const title = `Daily counts ${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)

  // --- a new console is an unnamed draft the server already holds ----------
  await page.getByTestId("new-query").click()
  await expect(page.getByTestId("query-state")).toHaveText("Saved")
  await expect(page.getByTestId("query-context")).toContainText(name)

  await typeQuery(page, "select 1 as answer")
  await expect(page.getByTestId("query-state")).toHaveText("Unsaved changes")
  await expect(page.getByTestId("query-state")).toHaveText("Saved")

  // --- naming it changes its title and nothing else ------------------------
  await page.getByTestId("query-title").fill(title)
  await expect(page.getByTestId("query-state")).toHaveText("Saved")
  // The tab takes the name, because a tab is what a person looks for.
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toContainText(title)

  // --- the text is the server's, not the browser's -------------------------
  await page.reload()
  await expect(page.locator(".cm-content")).toContainText("select 1 as answer")
  await expect(page.getByTestId("query-title")).toHaveValue(title)

  // --- and the library finds it by what is written in it -------------------
  await page.getByTestId("queries-search").fill(title)
  const row = page.locator('[data-testid^="query-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText(title)

  // --- deleting is Trash for thirty days, and Trash gives it back ----------
  await page.getByTestId("query-trash").click()
  await expect(page.locator(".q-notification", { hasText: "Trash" })).toBeVisible()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(0)
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  await page.getByTestId("queries-trash").click()
  const trashed = page.locator('[data-testid^="query-row-"]')
  await expect(trashed).toContainText(title)
  await trashed.locator('[data-testid^="restore-query-"]').click()
  await page.getByTestId("queries-trash").click()
  await expect(page.locator('[data-testid^="query-row-"]')).toContainText(title)

  // --- and deleting it for good is a second, deliberate step ---------------
  await page.locator('[data-testid^="trash-query-"]').click()
  await page.getByTestId("queries-trash").click()
  await page.locator('[data-testid^="purge-query-"]').click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId("queries-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("a query outlives the connection it was written against", async ({ page }) => {
  /** D63: losing the context does not lose the work. */
  const name = `e2e-query-orphan-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, "select 'kept'")
  await expect(page.getByTestId("query-state")).toHaveText("Saved")

  await deleteConnector(page, name)
  await page.reload()

  await expect(page.locator(".cm-content")).toContainText("select 'kept'")
  await expect(page.getByTestId("query-context")).toContainText("Connection unavailable")
})
