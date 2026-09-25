import { expect, test } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/**
 * One row of a relation, read downwards (D111).
 *
 * In the browser because the claim is about what a person ends up looking at:
 * every column of one row at once, with the keys it takes part in beside it,
 * and the next row a button away rather than a scroll away.
 */

test("reads one row downwards and walks to the next", async ({ page }) => {
  const name = `e2e-record-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "app_users")
  await expect(page.getByTestId("grid-cell-0-email")).toBeVisible()

  // The way in is on the row, and appears when the row is pointed at.
  await page.getByTestId("grid-row-0").hover()
  await page.getByTestId("grid-open-row-0").click()

  const view = page.getByTestId("record-view")
  await expect(view).toBeVisible()
  await expect(page.getByTestId("record-number")).toHaveCount(0)
  // What only the relation model knows, beside the value it belongs to.
  await expect(view.getByTestId("record-badge-primary_key").first()).toBeVisible()
  await expect(view).toContainText("organization_id")

  const navigation = view.getByTestId("record-navigation")
  const previous = view.getByTestId("record-previous")
  const next = view.getByTestId("record-next")
  const viewBox = await view.boundingBox()
  const navigationBox = await navigation.boundingBox()
  const previousBox = await previous.boundingBox()
  const nextBox = await next.boundingBox()
  if (
    viewBox === null ||
    navigationBox === null ||
    previousBox === null ||
    nextBox === null
  ) {
    throw new Error("the row view is not laid out")
  }
  expect(Math.round(navigationBox.y + navigationBox.height)).toBe(
    Math.round(viewBox.y + viewBox.height)
  )
  const previousInset = previousBox.x - navigationBox.x
  const nextInset = navigationBox.x + navigationBox.width - (nextBox.x + nextBox.width)
  expect(previousInset).toBeGreaterThanOrEqual(0)
  expect(previousInset).toBeLessThanOrEqual(16)
  expect(nextInset).toBeGreaterThanOrEqual(0)
  expect(nextInset).toBeLessThanOrEqual(16)

  const headings = ["Key", "Column", "Type", "Value"].map((name) =>
    view.getByRole("columnheader", { name, exact: true })
  )
  const columnsBefore = await Promise.all(headings.map((heading) => heading.boundingBox()))
  const first = await page.getByTestId("record-value-email").innerText()
  await next.click()
  await expect(page.getByTestId("record-value-email")).not.toHaveText(first)

  const columnsAfter = await Promise.all(headings.map((heading) => heading.boundingBox()))
  expect(columnsBefore.every((box) => box !== null)).toBe(true)
  expect(columnsAfter.every((box) => box !== null)).toBe(true)
  for (const [at, before] of columnsBefore.entries()) {
    const after = columnsAfter[at]
    if (before === null || after === null) throw new Error("a row-view column is missing")
    expect(Math.round(after.x)).toBe(Math.round(before.x))
    expect(Math.round(after.width)).toBe(Math.round(before.width))
  }
  const navigationAfter = await navigation.boundingBox()
  if (navigationAfter === null) throw new Error("the row navigation disappeared")
  expect(Math.round(navigationAfter.x)).toBe(Math.round(navigationBox.x))
  expect(Math.round(navigationAfter.y)).toBe(Math.round(navigationBox.y))
  expect(Math.round(navigationAfter.width)).toBe(Math.round(navigationBox.width))
  expect(Math.round(navigationAfter.height)).toBe(Math.round(navigationBox.height))

  // And the key of the row it is showing leads out of it, into a tab of its
  // own, exactly as the arrow in the grid does.
  await page.getByTestId("record-follow-organization_id").click()
  await expect(rowsTabs(page)).toHaveCount(1)
  await page.getByTestId("menu-item-app_users_organization_id_fkey").click()
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(rowsTabs(page).last()).toContainText("organizations")

  await deleteConnector(page, name)
})
