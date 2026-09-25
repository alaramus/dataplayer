import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, showOnlySchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

// Two catalogs of two connections in one window, and what goes between them
// (D167). The file source's personal directory holds `reports/q3.csv` once
// `app.seed_storage` has run.

function tabOf(page: Page, name: string) {
  return page.locator('[data-testid^="workspace-tab-catalog:"]', { hasText: name }).first()
}

/** Carry a tab to the header and drop it on Pair, as a person does. */
async function dropOnPair(page: Page, tab: Locator) {
  const from = await tab.boundingBox()
  if (from === null) throw new Error("The catalog tab has no rectangle")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2, from.y - 12, { steps: 4 })
  const target = page.getByTestId("workspace-pair-target")
  await expect(target).toBeVisible()
  const box = await target.boundingBox()
  if (box === null) throw new Error("The Pair target has no rectangle")
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 6 })
  await page.mouse.up()
}

test("pairs two catalogs by dropping them on Pair, and pastes between them", async ({ page }) => {
  const files = `e2e-pair-files-${Date.now()}`
  const database = `e2e-pair-db-${Date.now()}`
  const table = `paired_${Date.now()}`
  await login(page)
  await createFileConnector(page, files)
  await createPostgresConnector(page, database)
  await openConnector(page, files)
  await openConnector(page, database)
  await showOnlySchema(page, "demo_lab")

  // The first drop only waits: nothing opens, and the catalog stays.
  await dropOnPair(page, tabOf(page, files))
  await expect(page.getByTestId("pair-waiting")).toContainText(files)
  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await expect(tabOf(page, files)).toBeVisible()

  // The second opens the pair, both catalogs alive in it.
  await dropOnPair(page, tabOf(page, database))
  const pair = page.getByTestId("pair-window")
  await expect(pair).toBeVisible()
  await expect(page.getByTestId("pair-waiting")).toHaveCount(0)
  const left = page.getByTestId("pair-side-left")
  const right = page.getByTestId("pair-side-right")
  await expect(right.getByTestId("catalog-list")).toContainText("projects")
  // A catalog already in a pair is offered to no other, and leaves its own
  // menu and ×2 to the window.
  await expect(pair.getByTestId("catalog-pair")).toHaveCount(0)
  await expect(pair.getByTestId("catalog-actions")).toHaveCount(0)
  await expect(pair.getByTestId("catalog-duplicate")).toHaveCount(0)

  // One bar, left to right: before anything is ticked it says what could go
  // that way, and what to tick for it. Swap sides turns it round.
  const bar = page.getByTestId("pair-bar")
  await expect(bar).toContainText(`${files} → ${database}`)
  await expect(bar).toContainText("Tick a file or a table readable as rows")
  await page.getByTestId("pair-swap").click()
  await expect(bar).toContainText(`${database} → ${files}`)
  await expect(bar).toContainText("Tick a table or a view")
  await page.getByTestId("pair-swap").click()
  await expect(bar).toContainText(`${files} → ${database}`)
  await expect(bar).toContainText("Tick a file or a table readable as rows")

  // Each new tick is a new question, and the bar keeps the last answer until
  // the next arrives: collapsing to "Checking" made both catalogs jump.
  await bar.evaluate((element) => {
    const seen = { checking: false }
    Object.assign(window, { pairBarSeen: seen })
    new MutationObserver(() => {
      if (element.textContent?.includes("Checking what can be done")) seen.checking = true
    }).observe(element, { childList: true, subtree: true, characterData: true })
  })
  await left.getByTestId("catalog-node-reports").click()
  await left.getByTestId("catalog-check-q3.csv").click()
  await expect(page.getByTestId("pair-run-rows_new_relation")).toBeVisible()
  expect(await page.evaluate(() =>
    (window as unknown as { pairBarSeen: { checking: boolean } }).pairBarSeen.checking
  )).toBe(false)
  await page.getByTestId("pair-run-rows_new_relation").click()
  await page.getByTestId("grid-create-table-name").fill(table)
  await page.getByTestId("grid-create-table-run").click()
  await expect(right.getByTestId(`catalog-node-${table}`)).toBeVisible()

  // Closing the window takes the pair apart: both catalogs go home.
  await page.locator('[data-testid^="window-close-pair:"]').click()
  await expect(pair).toHaveCount(0)
  await expect(tabOf(page, files)).toBeVisible()
  await expect(tabOf(page, database)).toBeVisible()

  await tabOf(page, database).click()
  await catalogCheck(page, table).click()
  await catalogAction(page, "drop_relation")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, table)).toHaveCount(0)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
  await expect(connectorRow(page, database)).toHaveCount(0)
})

test("pairs without dragging: the catalog's own Pair and a connection from the list", async ({
  page,
}) => {
  const files = `e2e-pair-keys-files-${Date.now()}`
  const database = `e2e-pair-keys-db-${Date.now()}`
  await login(page)
  await createFileConnector(page, files)
  await createPostgresConnector(page, database)
  await openConnector(page, files)

  await page.getByTestId("catalog-pair").click()
  await expect(page.getByTestId("pair-waiting")).toContainText(files)
  await page.getByTestId("pair-waiting-choose").click()
  await page.getByRole("menuitem", { name: database, exact: true }).click()

  await expect(page.getByTestId("pair-window")).toBeVisible()
  await expect(page.getByTestId("pair-side-right").getByTestId("catalog-list")).toBeVisible()
  await expect(page.getByTestId("pair-side-left")).toContainText("reports")

  await page.locator('[data-testid^="window-close-pair:"]').click()
  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("a second catalog of the waiting connection is not taken", async ({ page }) => {
  const files = `e2e-pair-same-${Date.now()}`
  await login(page)
  await createFileConnector(page, files)
  await openConnector(page, files)
  await page.getByTestId("catalog-duplicate").click()

  await page.getByTestId("catalog-pair").first().click()
  const copies = page.locator('[data-testid^="workspace-tab-catalog:"]', { hasText: files })
  const copy = copies.nth(1)
  const from = await copy.boundingBox()
  if (from === null) throw new Error("The copy has no tab")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2, from.y - 12, { steps: 4 })
  await expect(page.getByTestId("workspace-pair-target")).toContainText("Pick another connection")
  await page.keyboard.press("Escape")
  await page.mouse.up()

  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await page.getByTestId("pair-waiting-cancel").click()
  await expect(page.getByTestId("pair-waiting")).toHaveCount(0)
  await deleteConnector(page, files)
})
