import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { arrowFor } from "./utils/tree"
import { connectorAction, connectorRow, openConnector } from "./utils/workspace"

test("browses a catalog from schema down to column", async ({ page }) => {
  const name = `e2e-catalog-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await openConnector(page, name)

  const tree = page.getByTestId("catalog-tree")
  await expect(tree).toContainText("public")

  await arrowFor(page, "public").click()
  await expect(tree).toContainText("connector")

  await arrowFor(page, "connector").click()
  // A column carries its data type, which only the catalog can supply.
  await expect(tree).toContainText("adapter_type")
  await expect(tree).toContainText("character varying")

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})
