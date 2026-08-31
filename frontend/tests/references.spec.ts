import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/**
 * Going from a row to the rows its foreign key names.
 *
 * In the browser because the whole point is what the user ends up looking at:
 * a second tab, on the relation the key pointed at, showing only the rows it
 * named. A unit test can prove the request; only this proves the arrival.
 */

/** The text of a cell without the controls that live in it. */
function cellValue(page: Page, testId: string) {
  return page.getByTestId(testId).locator("> span").first()
}

test("opens the referenced relation showing only the rows the key names", async ({
  page,
}) => {
  const name = `e2e-reference-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(page.getByTestId("grid-cell-0-organization_id")).toBeVisible()

  // The value alone: the arrow sits in the same cell, and an icon font puts
  // its ligature into the cell's text.
  const value = cellValue(page, "grid-cell-0-organization_id")
  const owner = (await value.innerText()).trim()
  await page.getByTestId("grid-cell-0-organization_id").hover()
  await page.getByTestId("grid-follow-0-projects_organization_id_fkey").click()

  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(rowsTabs(page).last()).toContainText("organizations")
  await page.getByTestId("grid-filter").hover()
  await expect(page.locator(".app-tooltip")).toHaveText("Filters (1)")
  await expect(page.getByTestId("grid-page-range")).toHaveText("Rows 1–1")
  await expect(cellValue(page, "grid-cell-0-organization_id")).toHaveText(owner)

  await deleteConnector(page, name)
})

test("draws no way out of a cell with nothing in it", async ({ page }) => {
  const name = `e2e-reference-null-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "teams")
  await expect(page.getByTestId("grid-cell-0-parent_team_id")).toBeVisible()

  // No seeded team has a parent, so that key stands empty. An empty cell has
  // nothing to act on, and the arrow of the other key is still there.
  await expect(cellValue(page, "grid-cell-0-parent_team_id")).toHaveText("null")
  await expect(page.getByTestId("grid-follow-0-teams_parent_team_id_fkey")).toHaveCount(0)
  await expect(
    page.getByTestId("grid-follow-0-teams_organization_id_fkey")
  ).toHaveCount(1)

  await deleteConnector(page, name)
})
