import { expect, test } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { nodeHeader } from "./utils/tree"
import { connectorAction, connectorRow, openConnector } from "./utils/workspace"

test("creates, fills, renames and removes a folder in personal storage", async ({
  page,
}) => {
  const name = `e2e-actions-${Date.now()}`
  const folder = `batch-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const tree = page.getByTestId("catalog-tree")
  await expect(tree).toContainText("reports")

  // Nothing selected: the actions offered are the ones the root admits, and
  // removing the root is not among them.
  await expect(page.getByTestId("action-create_folder")).toBeVisible()
  await expect(page.getByTestId("action-upload")).toBeVisible()
  await expect(page.getByTestId("action-delete")).toHaveCount(0)

  // --- create a folder, and see it appear without reopening the dialog
  await page.getByTestId("action-create_folder").click()
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(tree).toContainText(folder)

  // --- upload a file into it
  await nodeHeader(page, folder).click()
  await expect(page.getByTestId("action-rename")).toBeVisible()
  await page.getByTestId("action-upload").click()
  // Quasar puts data-testid on the input itself, so it is addressed directly.
  await page.getByTestId("action-file").setInputFiles({
    name: "uploaded.csv",
    mimeType: "text/csv",
      buffer: Buffer.from("id,name\n1,one\n2,two\n"),
    })
  await page.getByTestId("action-submit").click()
  await expect(tree).toContainText("uploaded.csv")

  // --- what was uploaded is readable, which proves the bytes arrived whole
  await nodeHeader(page, "uploaded.csv").click()
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid.locator("tbody tr")).toHaveCount(2)

  // --- rename it. The tree is a column of its own, so it never went away.
  await page.getByTestId("action-rename").click()
  await page
    .getByTestId("action-dialog")
    .getByRole("textbox")
    .first()
    .fill("renamed.csv")
  await page.getByTestId("action-submit").click()
  await expect(tree).toContainText("renamed.csv")
  await expect(tree).not.toContainText("uploaded.csv")

  // --- a folder with something inside refuses to go quietly
  await nodeHeader(page, folder).click()
  await page.getByTestId("action-delete").click()
  await expect(page.getByTestId("action-warning")).toContainText("cannot be undone")
  await page.getByTestId("action-submit").click()
  await expect(page.getByTestId("action-error")).toContainText("not empty")

  // --- saying so explicitly removes it
  await page.getByTestId("field-recursive").click()
  await page.getByTestId("action-submit").click()
  await expect(tree).not.toContainText(folder)

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a database offers no actions at all", async ({ page }) => {
  const name = `e2e-actions-pg-${Date.now()}`
  await login(page)

  await createPostgresConnector(page, name)

  await openConnector(page, name)
  await expect(page.getByTestId("catalog-tree")).toContainText("public")
  // The source does not implement the capability, so the bar has nothing to
  // show — and the screen says so by being empty, not by an error.
  await expect(page.getByTestId("action-bar")).toHaveCount(0)
  await expect(page.getByTestId("catalog-error")).toHaveCount(0)

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})
