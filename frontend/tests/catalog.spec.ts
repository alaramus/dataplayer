import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { connectionsTab } from "./utils/workspace"

// The backend runs the queries, not the browser, so the address is written as
// the backend container sees it: inside the compose network the database is db.
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

/** The expand arrow of the tree node with the given label.
 *
 * The header text is not anchored: the custom header renders the icon first,
 * so the node name never starts the string.
 */
function arrowFor(page: import("@playwright/test").Page, label: string) {
  return page
    .locator(".q-tree__node-header", { hasText: label })
    .first()
    .locator(".q-tree__arrow")
}

test("browses a catalog from schema down to column", async ({ page }) => {
  const name = `e2e-catalog-${Date.now()}`
  await login(page)
  await createConnector(page, name)

  await page.getByTestId(`browse-${name}`).click()

  const tree = page.getByTestId("catalog-tree")
  await expect(tree).toContainText("public")

  await arrowFor(page, "public").click()
  await expect(tree).toContainText("connector")

  await arrowFor(page, "connector").click()
  // A column carries its data type, which only the catalog can supply.
  await expect(tree).toContainText("adapter_type")
  await expect(tree).toContainText("character varying")

  // The catalog opened as a tab beside the connections rather than in a modal,
  // so the way back to the table is its tab.
  await connectionsTab(page).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})
