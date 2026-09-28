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

/**
 * Offer a catalog with its own Pair command, as a person does: its tab is
 * brought forward and the button pressed. The header takes no carried tab.
 */
async function offerToPair(page: Page, tab: Locator) {
  await tab.click()
  await page.locator('[data-testid="catalog-pair"]:visible').click()
}

test("pairs two catalogs with their Pair command, and pastes between them", async ({ page }) => {
  const files = `e2e-pair-files-${Date.now()}`
  const database = `e2e-pair-db-${Date.now()}`
  const table = `paired_${Date.now()}`
  await login(page)
  await createFileConnector(page, files)
  await createPostgresConnector(page, database)
  await openConnector(page, files)
  await openConnector(page, database)
  await showOnlySchema(page, "demo_lab")

  // The first only waits: nothing opens, and the catalog stays.
  await offerToPair(page, tabOf(page, files))
  await expect(page.getByTestId("pair-waiting")).toContainText(files)
  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await expect(tabOf(page, files)).toBeVisible()

  // The second opens the pair, both catalogs alive in it.
  await offerToPair(page, tabOf(page, database))
  const pair = page.getByTestId("pair-window")
  await expect(pair).toBeVisible()
  await expect(page.getByTestId("pair-waiting")).toHaveCount(0)
  const left = page.getByTestId("pair-side-left")
  const right = page.getByTestId("pair-side-right")
  await expect(right.getByTestId("catalog-list")).toContainText("projects")
  // A catalog already in a pair is offered to no other, and leaves its own
  // menu and Duplicate to the window.
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
  // The copy's own Pair is greyed rather than gone, and says why: a pair of
  // one connection would have nothing to show between its sides.
  await expect(page.getByTestId("catalog-pair").nth(1)).toBeDisabled()
  await expect(
    page.getByRole("button", {
      name: "Pair with another connection — a catalog of this connection is already waiting",
    })
  ).toBeVisible()

  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await page.getByTestId("pair-waiting-cancel").click()
  await expect(page.getByTestId("pair-waiting")).toHaveCount(0)
  await deleteConnector(page, files)
})
