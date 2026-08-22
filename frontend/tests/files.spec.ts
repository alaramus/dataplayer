import { expect, test } from "@playwright/test"

import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { nodeHeader } from "./utils/tree"
import { connectorAction, connectorRow, openConnector, rowsTabs } from "./utils/workspace"

// The samples come from `docker compose exec backend python -m app.seed_storage`:
// this sub-project cannot write files, so a personal directory is empty until
// that script has run.
test("browses a personal directory and reads files as rows", async ({ page }) => {
  const name = `e2e-files-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  await openConnector(page, name)

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

  // The tree is a column of its own, so nothing covered it and nothing had to
  // be clicked to get back to it - and it is still expanded where it was.
  await nodeHeader(page, "notes.txt").click()
  await expect(grid).toContainText("line_no")
  await expect(grid).toContainText("line 1")

  // A file nothing can read as rows opens no tab: two remain, and the grid
  // still shows the file that was read last.
  await nodeHeader(page, "logo.png").click()
  await expect(page.getByTestId("opaque-file")).toContainText("cannot be read")
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(grid).toContainText("line_no")

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})
