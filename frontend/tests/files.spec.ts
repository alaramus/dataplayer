import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"
import { catalogTab, connectionsTab } from "./utils/workspace"

// The samples come from `docker compose exec backend python -m app.seed_storage`:
// this sub-project cannot write files, so a personal directory is empty until
// that script has run.
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

test("browses a personal directory and reads files as rows", async ({ page }) => {
  const name = `e2e-files-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  await page.getByTestId(`browse-${name}`).click()

  const tree = page.getByTestId("catalog-tree")
  await expect(tree).toContainText("reports")
  await expect(tree).toContainText("sample.csv")
  await expect(tree).toContainText("notes.txt")
  // The size is a caption, and QTree has no caption prop: it only appears
  // because the header slot renders it. Asserted here because a unit test of
  // the mapper passed once while nothing reached the screen.
  await expect(tree).toContainText(/\d+(\.\d+)? KB/)

  await nodeHeader(page, "sample.csv").click()
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("population")
  await expect(grid.locator("tbody tr")).toHaveCount(50)
  // A file has no row estimate: counting means reading it end to end, so the
  // grid pages without ever claiming a total.
  await expect(page.getByTestId("row-grid")).toContainText("Rows 1–50")
  await expect(page.getByTestId("row-grid")).not.toContainText("of ~")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 51–100")

  // Back to the tree: the rows of the previous file are covering it, and the
  // tab that comes back is the one that was left, expanded as it was.
  await catalogTab(page).click()
  await nodeHeader(page, "notes.txt").click()
  await expect(grid).toContainText("line_no")
  await expect(grid).toContainText("line 1")

  await catalogTab(page).click()
  await nodeHeader(page, "logo.png").click()
  await expect(page.getByTestId("opaque-file")).toContainText("cannot be read")
  await expect(page.getByTestId("row-grid")).toHaveCount(0)

  // The catalog opened as a tab beside the connections rather than in a modal,
  // so the way back to the table is its tab.
  await connectionsTab(page).click()
  await page.getByTestId(`delete-${name}`).click()
  await page.getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId("connector-table")).not.toContainText(name)
})
