import { expect, test } from "@playwright/test"

import { catalogRow, openNode } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

// The samples come from `docker compose exec backend python -m app.seed_storage`:
// this sub-project cannot write files, so a personal directory is empty until
// that script has run.
test("browses a personal directory and reads files as rows", async ({ page }) => {
  const name = `e2e-files-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("reports")
  await expect(list).toContainText("sample.csv")
  await expect(list).toContainText("notes.txt")
  // The size is a caption of the row. Asserted here because a unit test of the
  // mapper passed once while nothing reached the screen.
  await expect(list).toContainText(/\d+(\.\d+)? KB/)

  // Nothing has been walked into yet, so there is no path to show.
  await expect(page.getByTestId("catalog-path")).toHaveCount(0)

  // A directory is walked into, and the path says where we are.
  await openNode(page, "reports")
  await expect(page.getByTestId("catalog-path")).toContainText("reports")

  // It shares the line with the icon of the source and the menu: a column
  // this narrow cannot afford a stack of them, and a unit test cannot tell
  // one line from two.
  const icon = await page.getByTestId("catalog-connector").boundingBox()
  const path = await page.getByTestId("catalog-path").boundingBox()
  const middle = (box: { y: number; height: number } | null) =>
    box === null ? 0 : box.y + box.height / 2
  expect(Math.abs(middle(icon) - middle(path))).toBeLessThan(4)
  await expect(list).toContainText("q3.csv")

  // The way back is the first row of the list, as it is in any other
  // explorer, rather than a button in the head.
  await expect(list.locator("> div").first()).toHaveAttribute(
    "data-testid",
    "catalog-up"
  )
  // It lines up with the rows that have a tick box: the space is reserved by
  // the control itself, so nothing here depends on guessing how wide it is.
  const back = await page.getByTestId("catalog-up").getByText("..").boundingBox()
  const beside = await catalogRow(page, "q3.csv").getByText("q3.csv").boundingBox()
  expect(Math.abs((back?.x ?? 0) - (beside?.x ?? 0))).toBeLessThan(1)

  await page.getByTestId("catalog-up").click()
  await expect(list).toContainText("sample.csv")
  await expect(page.getByTestId("catalog-up")).toHaveCount(0)

  // And the path starts at a home button rather than at the name of the
  // connection, which is already on the tab above it.
  await openNode(page, "reports")
  await page.getByTestId("catalog-home").click()
  await expect(list).toContainText("sample.csv")

  await openNode(page, "sample.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("population")
  await expect(grid.locator("tbody tr")).toHaveCount(50)
  // A file has no row estimate: counting means reading it end to end, so the
  // grid pages without ever claiming a total.
  await expect(grid).toContainText("Rows 1–50")
  await expect(grid).not.toContainText("of ~")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 51–100")

  // The list is a column of its own, so nothing covered it and nothing had to
  // be clicked to get back to it.
  await openNode(page, "notes.txt")
  await expect(grid).toContainText("line_no")
  await expect(grid).toContainText("line 1")

  // A file nothing can read as rows opens no tab, and says so: two remain, and
  // the grid still shows the file that was read last.
  await openNode(page, "logo.png")
  // Named rather than "the notification": several may still be on screen.
  await expect(
    page.locator(".q-notification", { hasText: "cannot be read" })
  ).toBeVisible()
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(grid).toContainText("line_no")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
