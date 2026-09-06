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

test("keeps a key's corner mark under the column pinned over it", async ({
  page,
}) => {
  // Only a browser answers this. The mark and a pinned column were on the same
  // layer, so the one later in the row won: the mark of a column scrolled
  // underneath was drawn on top of the column that is there to hide it.
  const name = `e2e-reference-pinned-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await expect(
    page.getByTestId("grid-follow-0-projects_organization_id_fkey")
  ).toBeVisible()

  await page.getByTestId("grid-pin-name").click()
  const scroll = page.locator(".data-grid__scroll").first()
  await expect(scroll.locator("td.data-grid__pinned").first()).toBeVisible()

  // Put the mark exactly behind the pinned column, wherever the two are.
  await scroll.evaluate((box) => {
    const mark = box.querySelector(
      '[data-testid="grid-follow-0-projects_organization_id_fkey"]'
    )
    const pinned = box.querySelector("td.data-grid__pinned")
    if (mark === null || pinned === null) throw new Error("nothing to line up")
    const one = mark.getBoundingClientRect()
    const other = pinned.getBoundingClientRect()
    box.scrollLeft += one.left + one.width / 2 - (other.left + other.width / 2)
  })
  await expect.poll(() => scroll.evaluate((box) => box.scrollLeft)).toBeGreaterThan(0)

  const painted = await page.evaluate(() => {
    const mark = document.querySelector(
      '[data-testid="grid-follow-0-projects_organization_id_fkey"]'
    )
    const pinned = document.querySelector("td.data-grid__pinned")
    if (mark === null || pinned === null) return "nothing to look at"
    const one = mark.getBoundingClientRect()
    const other = pinned.getBoundingClientRect()
    const x = one.left + one.width / 2
    const y = one.top + one.height / 2
    if (x < other.left || x > other.right || y < other.top || y > other.bottom) {
      return "the mark did not end up behind the pinned column"
    }
    return document.elementFromPoint(x, y)?.closest("td")?.className ?? "nothing"
  })
  expect(painted).toContain("data-grid__pinned")

  await deleteConnector(page, name)
})
