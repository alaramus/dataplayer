import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test("creates, fills, renames and removes a folder in personal storage", async ({
  page,
}) => {
  const name = `e2e-actions-${Date.now()}`
  const folder = `batch-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("reports")

  // Nothing ticked: the menu offers what the level being looked at admits, and
  // removing the root of a connector is not among that.
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-create_folder")).toBeVisible()
  await expect(page.getByTestId("menu-item-upload")).toBeVisible()
  await expect(page.getByTestId("menu-item-delete")).toHaveCount(0)
  await page.keyboard.press("Escape")

  // --- create a folder, and see it appear without reopening the dialog
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText(folder)

  // --- upload a file into it. The folder is walked into, not ticked: an
  // upload belongs to the directory one is looking at.
  await openNode(page, folder)
  await catalogAction(page, "upload")
  // Quasar puts data-testid on the input itself, so it is addressed directly.
  await page.getByTestId("action-file").setInputFiles({
    name: "uploaded.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,name\n1,one\n2,two\n"),
  })
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("uploaded.csv")

  // --- what was uploaded is readable, which proves the bytes arrived whole
  await openNode(page, "uploaded.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid.locator("tbody tr")).toHaveCount(2)

  // --- rename it. Ticking picks it out without opening it again.
  await catalogCheck(page, "uploaded.csv").click()
  await catalogAction(page, "rename")
  await page
    .getByTestId("action-dialog")
    .getByRole("textbox")
    .first()
    .fill("renamed.csv")
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("renamed.csv")
  await expect(list).not.toContainText("uploaded.csv")

  // --- a folder with something inside refuses to go quietly
  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await expect(page.getByTestId("action-warning")).toContainText("cannot be undone")
  await page.getByTestId("action-submit").click()
  await expect(page.getByTestId("action-error")).toContainText("not empty")

  // --- saying so explicitly removes it
  await page.getByTestId("field-recursive").click()
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("two files at once admit only what can be done to many", async ({ page }) => {
  const name = `e2e-bulk-${Date.now()}`
  const first = `bulk-a-${Date.now()}`
  const second = `bulk-b-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  for (const folder of [first, second]) {
    await catalogAction(page, "create_folder")
    await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
    await page.getByTestId("action-submit").click()
    await expect(page.getByTestId("catalog-list")).toContainText(folder)
  }

  await catalogCheck(page, first).click()
  await catalogCheck(page, second).click()

  // Renaming two folders to one name is not two renames, and the action says
  // so itself — the server leaves it out of the answer.
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-delete")).toBeVisible()
  await expect(page.getByTestId("menu-item-rename")).toHaveCount(0)
  await page.getByTestId("menu-item-delete").click()

  await page.getByTestId("action-submit").click()
  // One line for the whole set, and both are gone.
  await expect(page.locator(".q-notification", { hasText: "2 of 2" })).toBeVisible()
  await expect(catalogRow(page, first)).toHaveCount(0)
  await expect(catalogRow(page, second)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a database offers no actions at all", async ({ page }) => {
  const name = `e2e-actions-pg-${Date.now()}`
  await login(page)

  await createPostgresConnector(page, name)

  await openConnector(page, name)
  await expect(page.getByTestId("catalog-list")).toContainText("connector")
  // The source does not implement the capability, so the menu has nothing to
  // show — and the screen says so by offering nothing, not by an error.
  await expect(page.getByTestId("catalog-actions")).toBeDisabled()
  await expect(page.getByTestId("catalog-error")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
