import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test("shows the structure of a relation beside its rows", async ({ page }) => {
  const name = `e2e-structure-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await page.getByTestId("catalog-structure-app_users").click()

  const view = page.getByTestId("structure-view")
  await expect(view).toBeVisible()
  await expect(view).toContainText("user_id")
  await expect(view).toContainText("bigint")
  await expect(view.getByTestId("structure-badge-primary_key").first()).toBeVisible()
  await expect(view.getByTestId("structure-fk").first()).toContainText(
    "demo_lab.organizations"
  )

  await openNode(page, "app_users")
  await expect(page.getByTestId("row-grid")).toBeVisible()

  // Put the inactive structure tab in a section of its own, leaving rows in
  // the work section that new panels target.
  const structureTab = page.locator('[data-testid^="workspace-tab-structure:"]').first()
  const work = page.getByTestId("workspace-leaf-work")
  const from = await structureTab.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the structure tab has no box")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width * 0.1, onto.y + onto.height * 0.6, { steps: 12 })
  await page.mouse.up()

  await expect(view).toBeVisible()
  await expect(page.getByTestId("row-grid")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
