import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"

// The backend runs the queries, so the address is the one the backend
// container sees.
const DATABASE = {
  host: process.env.POSTGRES_SERVER ?? "db",
  port: process.env.POSTGRES_PORT ?? "5432",
  database: process.env.POSTGRES_DB ?? "app",
  user: process.env.POSTGRES_USER ?? "postgres",
  password: process.env.POSTGRES_PASSWORD ?? "",
}

async function createFileConnector(page: Page, name: string) {
  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "Files" }).click()
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("connector-table")).toContainText(name)
}

function nodeHeader(page: Page, label: string) {
  return page.locator(".q-tree__node-header", { hasText: label }).first()
}

test("creates, fills, renames and removes a folder in personal storage", async ({
  page,
}) => {
  const name = `e2e-actions-${Date.now()}`
  const folder = `batch-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await page.getByTestId(`browse-${name}`).click()

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

  // --- rename it
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

  await page.getByRole("button", { name: "Close" }).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})

test("a database offers no actions at all", async ({ page }) => {
  const name = `e2e-actions-pg-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "PostgreSQL" }).click()
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(page.getByTestId("connector-table")).toContainText(name)

  await page.getByTestId(`browse-${name}`).click()
  await expect(page.getByTestId("catalog-tree")).toContainText("public")
  // The source does not implement the capability, so the bar has nothing to
  // show — and the screen says so by being empty, not by an error.
  await expect(page.getByTestId("action-bar")).toHaveCount(0)
  await expect(page.getByTestId("catalog-error")).toHaveCount(0)

  await page.getByRole("button", { name: "Close" }).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})
