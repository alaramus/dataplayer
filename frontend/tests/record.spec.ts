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
  await expect(page.getByTestId("record-number")).toHaveText("Row 1")
  // What only the relation model knows, beside the value it belongs to.
  await expect(view.getByTestId("record-badge-primary_key").first()).toBeVisible()
  await expect(view).toContainText("organization_id")

  const first = await page.getByTestId("record-value-email").innerText()
  await page.getByTestId("record-next").click()
  await expect(page.getByTestId("record-number")).toHaveText("Row 2")
  await expect(page.getByTestId("record-value-email")).not.toHaveText(first)

  // And the key of the row it is showing leads out of it, into a tab of its
  // own, exactly as the arrow in the grid does.
  await page.getByTestId("record-follow-organization_id").click()
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(rowsTabs(page).last()).toContainText("organizations")

  await deleteConnector(page, name)
})
