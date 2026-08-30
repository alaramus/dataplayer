import { expect, test } from "@playwright/test"

import { catalogRow, openNode } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import {
  catalogTabIcon,
  connectorRow,
  deleteConnector,
  openConnector,
  rowsTabs,
} from "./utils/workspace"

// The samples come from `docker compose exec backend python -m app.seed_storage`:
// this sub-project cannot write files, so a personal directory is empty until
// that script has run.
test("browses a personal directory and opens each implemented viewer", async ({ page }) => {
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

  // The path is always visible for a file source, even at the top.
  await expect(page.getByTestId("catalog-path")).toBeVisible()
  await expect(page.getByTestId("catalog-home")).toBeVisible()

  // A directory is walked into, and the path says where we are.
  await openNode(page, "reports")
  await expect(page.getByTestId("catalog-path")).toContainText("reports")

  // The source icon lives on the tab, not in the head - the head holds
  // the path and the menu on one line.
  await expect(catalogTabIcon(page)).toBeVisible()
  await expect(list).toContainText("q3.csv")

  // The way back is the first row of the list, as it is in any other
  // explorer, rather than a button in the head.
  await expect(list.locator("> div").first()).toHaveAttribute("data-testid", "catalog-up")
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
  await expect(grid.locator("tbody tr")).toHaveCount(100)
  // A file has no row estimate: counting means reading it end to end, so the
  // grid pages without ever claiming a total.
  await expect(grid).toContainText("Rows 1–100")
  await expect(grid).not.toContainText("of ~")

  await page.getByTestId("grid-next").click()
  await expect(grid).toContainText("Rows 101–200")

  // The list is a column of its own, so nothing covered it and nothing had to
  // be clicked to get back to it.
  await openNode(page, "notes.txt")
  await expect(page.getByTestId("text-content")).toContainText("line 1")
  await expect(page.getByTestId("content-view-table")).toBeVisible()

  // A file with no implemented viewer opens no tab and says so.
  await openNode(page, "logo.png")
  // Named rather than "the notification": several may still be on screen.
  await expect(page.locator(".q-notification", { hasText: "has no viewer yet" })).toBeVisible()
  await expect(rowsTabs(page)).toHaveCount(1)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens JSON natively and turns it into a table only when asked", async ({ page }) => {
  const name = `e2e-json-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // Opening the file preserves the document. A number no JavaScript float
  // could hold arrives as lossless text in the JSON tree.
  await openNode(page, "people.json")
  await expect(page.getByTestId("json-content")).toContainText("10000000000000001")
  await expect(page.getByTestId("row-grid")).toHaveCount(0)

  // The table is an alternative representation, opened by an explicit act.
  await page.getByTestId("content-view-table").click()
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid).toContainText("city")
  await expect(grid.locator("tbody tr")).toHaveCount(3)

  // JSONL keeps its record boundary and physical line numbers in its viewer.
  await openNode(page, "events.jsonl")
  await expect(page.getByTestId("jsonl-content")).toContainText("Line 1")
  await expect(page.getByTestId("jsonl-content")).toContainText("login")

  // A file named .json that is not JSON stays in the JSON viewer, showing its
  // own source and the parser's precise refusal instead of becoming a table.
  await openNode(page, "broken.json")
  await expect(page.getByTestId("json-source")).toContainText('"b" 2')
  await expect(page.getByTestId("content-notice")).toContainText("not valid JSON")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
