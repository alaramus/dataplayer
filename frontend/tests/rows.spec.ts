import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

const DATABASE = {
  host: process.env.POSTGRES_SERVER ?? "db",
  port: process.env.POSTGRES_PORT ?? "5432",
  database: process.env.POSTGRES_DB ?? "app",
  user: process.env.POSTGRES_USER ?? "postgres",
  password: process.env.POSTGRES_PASSWORD ?? "",
}

async function createConnector(page: import("@playwright/test").Page, name: string) {
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
}

function nodeHeader(page: import("@playwright/test").Page, label: string) {
  return page.locator(".q-tree__node-header", { hasText: label }).first()
}

test("shows rows of a selected relation and pages through them", async ({ page }) => {
  const name = `e2e-rows-${Date.now()}`
  await login(page)
  await createConnector(page, name)

  await page.getByTestId(`browse-${name}`).click()
  // pg_catalog is used rather than an application table: it always holds
  // hundreds of rows, so paging is real rather than vacuous.
  await nodeHeader(page, "pg_catalog").locator(".q-tree__arrow").click()
  await nodeHeader(page, "pg_class").click()

  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("relname")
  await expect(grid.locator("tbody tr")).toHaveCount(50)
  await expect(grid).toContainText("Rows 1–50")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 51–100")

  await page.getByTestId("grid-prev").click()
  await expect(grid).toContainText("Rows 1–50")

  await page.getByRole("button", { name: "Close" }).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})
