import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/**
 * A reference somebody draws between two sources, and the jump it allows.
 *
 * In the browser because that is the whole claim: a column of a PostgreSQL
 * relation and a column of a CSV in personal storage are joined by nothing but
 * this application, and following the arrow lands in the other connection
 * showing the row it names (D106, D108). A unit test can prove the request;
 * only this proves the arrival.
 */

/** The text of a cell without the controls that live in it. */
function cellValue(page: Page, testId: string) {
  return page.getByTestId(testId).locator("> span").first()
}

async function choose(page: Page, testId: string, option: string) {
  await page.getByTestId(testId).click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test("joins a relation to a CSV and follows it into the other connection", async ({
  page,
}) => {
  const database = `e2e-declared-db-${Date.now()}`
  const files = `e2e-declared-files-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)
  await openConnector(page, database)
  await pickSchema(page, "demo_lab")
  await openNode(page, "organizations")
  await expect(page.getByTestId("grid-cell-0-organization_id")).toBeVisible()

  // The value this row holds, read before anything is drawn: the sample CSV
  // has a row for every id up to 250, so the jump has somewhere to land.
  const owner = (await cellValue(page, "grid-cell-0-organization_id").innerText()).trim()

  await page.getByTestId("grid-structure").click()
  const view = page.getByTestId("structure-view")
  await expect(view).toBeVisible()
  await view.getByTestId("structure-declare-reference").click()

  const dialog = page.getByTestId("declare-reference-dialog")
  await expect(dialog).toBeVisible()
  await choose(page, "declare-reference-near-column", "organization_id")
  await choose(page, "declare-reference-source", files)
  await page.getByTestId("declare-reference-node-sample.csv").click()
  await choose(page, "declare-reference-far-column", "id")
  await page.getByTestId("declare-reference-run").click()
  await expect(dialog).toBeHidden()

  await expect(view.getByTestId("declared-reference")).toContainText(
    `organization_id → ${files} · sample.csv.id`
  )

  // Back to the rows, where the arrow is now drawn in that column's cells.
  await page.locator('[data-testid^="workspace-tab-rows:"]').first().click()
  const arrow = page.locator('[data-testid^="grid-follow-0-declared:"]')
  await expect(arrow).toHaveCount(1)
  await page.getByTestId("grid-cell-0-organization_id").hover()
  await arrow.click()

  // A second tab, on the other connection, showing the row the value names.
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(rowsTabs(page).last()).toContainText("sample.csv")
  await expect(page.getByTestId("grid-page-range")).toHaveText("Rows 1–1")
  await expect(cellValue(page, "grid-cell-0-id")).toHaveText(owner)
  await expect(cellValue(page, "grid-cell-0-name")).toHaveText(`city-${owner}`)

  await deleteConnector(page, database)
  await deleteConnector(page, files)
})
