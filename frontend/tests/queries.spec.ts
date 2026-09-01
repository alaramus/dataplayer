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


test("runs the statement under the caret, then the whole script", async ({ page }) => {
  const name = `e2e-run-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  // --- one statement, from the keyboard ------------------------------------
  await typeQuery(page, "select 41 + 1 as answer")
  await page.keyboard.press("ControlOrMeta+Enter")

  const outcome = page.getByTestId("run-outcome")
  await expect(outcome).toBeVisible()
  await expect(page.getByTestId("run-statement-0")).toContainText("succeeded")
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("42")

  // --- several, only when the command says so ------------------------------
  await typeQuery(page, "select 1 as one;\nselect 2 as two")
  await page.getByTestId("query-run-script").click()
  await expect(page.getByTestId("run-statement-1")).toBeVisible()
  await page.getByTestId("run-statement-1").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("2")

  // --- an error is an output, not a toast that disappears -------------------
  await typeQuery(page, "select * from nothing_here")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-error")).toContainText("nothing_here")

  // --- and what the run said is in one chronological place -----------------
  await page.getByTestId("run-messages-tab").click()
  await expect(page.getByTestId("run-messages")).toContainText("MISSING_OBJECT")

  await deleteConnector(page, name)
})

test("asks for the values a query needs, and keeps the ones it is told to", async ({
  page,
}) => {
  const name = `e2e-parameters-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  await typeQuery(page, "select count(*) from generate_series(1, 10) i where i > :from_here")
  await expect(page.getByTestId("parameter-from_here")).toBeVisible()
  // Nothing to run until the question is answered.
  await expect(page.getByTestId("query-run")).toBeDisabled()

  await page.getByTestId("parameter-value-from_here").fill("7")
  await page.getByTestId("parameter-remember-from_here").click()
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("3")

  // The value was remembered with the document, so a reload brings it back.
  await page.reload()
  await expect(page.getByTestId("parameter-value-from_here")).toHaveValue("7")

  await deleteConnector(page, name)
})

test("a captured result is paged, ordered and opened in a panel of its own", async ({
  page,
}) => {
  const name = `e2e-result-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()

  await typeQuery(page, "select i from generate_series(1, 12) i")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  // Ordering acts on the captured rows and needs no second execution.
  await page.getByTestId("grid-sort-direction-0").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")
  await page.getByTestId("grid-sort-direction-0").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("12")

  // And the result can leave the console for a tab of its own (D65).
  await page.getByTestId("run-promote").click()
  await expect(page.locator('[data-testid^="workspace-tab-result:"]')).toHaveCount(1)

  await deleteConnector(page, name)
})


test("history keeps what ran, opens it again and can be deleted", async ({ page }) => {
  const name = `e2e-history-${Date.now()}`
  const marker = `select 'history-${Date.now()}' as kept`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, marker)
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("run-statement-0")).toContainText("succeeded")

  // --- what ran is in history, by what was written in it -------------------
  await page.getByTestId("queries-history").click()
  await page.getByTestId("queries-search").fill(marker)
  const row = page.locator('[data-testid^="history-row-"]')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText("succeeded")

  // --- and it opens again as a console of its own --------------------------
  await row.locator('[data-testid^="history-restore-"]').click()
  await expect(page.locator('[data-testid^="workspace-tab-query:"]')).toHaveCount(2)

  // --- deleting a run leaves nothing behind --------------------------------
  await row.locator('[data-testid^="history-delete-"]').click()
  await expect(page.getByTestId("history-empty")).toBeVisible()

  await deleteConnector(page, name)
})

test("a captured page can be charted where it is", async ({ page }) => {
  const name = `e2e-chart-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openQueries(page, name)
  await page.getByTestId("new-query").click()
  await typeQuery(page, "select i, i * 2 as doubled from generate_series(1, 5) i")
  await page.getByTestId("query-run").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  await page.getByTestId("result-chart").click()

  // The same bounded chart the grid has, over the rows on screen (D35).
  await expect(page.getByTestId("chart-type")).toBeVisible()
  await expect(page.locator("canvas, svg").first()).toBeVisible()

  await page.getByTestId("result-chart-close").click()
  await expect(page.getByTestId("grid-cell-0-0")).toHaveText("1")

  await deleteConnector(page, name)
})
