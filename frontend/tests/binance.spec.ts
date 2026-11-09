import { expect, test } from "@playwright/test"

import type { Page } from "@playwright/test"

import { catalogRow, openNode } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { canvasRow, drawLink } from "./utils/pipelines"
import { signedApi } from "./utils/search"
import { deleteConnector, openConnector } from "./utils/workspace"

type Api = { base: string; headers: Record<string, string> }

/** A Binance connection, or the scenario skipped where the server cannot reach Binance. */
async function binanceConnection(page: Page, api: Api, name: string): Promise<string> {
  const made = await page.request.post(`${api.base}/connectors/`, {
    headers: api.headers,
    data: { name, adapter_type: "binance", options: { endpoint: "binance" } },
  })
  expect(made.ok(), await made.text()).toBeTruthy()
  const id = ((await made.json()) as { id: string }).id
  const checked = await page.request.post(`${api.base}/connectors/${id}/check`, {
    headers: api.headers,
    data: {},
  })
  const reachable = checked.ok() && ((await checked.json()) as { ok: boolean }).ok
  if (!reachable) {
    await page.request.delete(`${api.base}/connectors/${id}`, { headers: api.headers })
    test.skip(true, "Binance does not answer from this server")
  }
  return id
}

/**
 * Binance's public market data in the catalog and the grid (D316–D318): a
 * market holds its lists and quote assets, a symbol its feeds, and a feed
 * opens as rows. It reads the real Binance, so it is skipped where the
 * server cannot reach it.
 */
test("walks from a market to a symbol and reads its feeds as rows", async ({ page }) => {
  const name = `e2e-binance-${Date.now()}`
  await login(page)
  const api = await signedApi(page)
  await binanceConnection(page, api, name)

  await page.reload()
  await openConnector(page, name)
  // The connection's own section first, its reports opening as rows (D320).
  await openNode(page, "Exchange")
  await openNode(page, "Rate limit")
  await expect(page.getByTestId("grid-cell-0-Setting")).toHaveText("Spot: limit a minute")
  await page.getByTestId("catalog-home").click()
  await expect(catalogRow(page, "Spot")).toBeVisible()
  await expect(catalogRow(page, "USDⓈ-M futures")).toBeVisible()
  await openNode(page, "Spot")
  await expect(catalogRow(page, "Tickers")).toBeVisible()
  await expect(catalogRow(page, "USDT")).toBeVisible()
  // Nothing in the menu acts on market data, so no row carries a box.
  await expect(page.getByTestId("catalog-check-USDT")).toHaveCount(0)
  await expect(page.getByTestId("catalog-check-all")).toHaveCount(0)

  // Tickers open as a page of rows, the busiest first.
  await openNode(page, "Tickers")
  await expect(page.getByTestId("grid-column-quote_volume")).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-symbol")).not.toBeEmpty()

  await openNode(page, "USDT")
  await openNode(page, "BTCUSDT")
  await expect(catalogRow(page, "Candles")).toBeVisible()
  await expect(catalogRow(page, "Trades")).toBeVisible()

  await openNode(page, "Order book")
  await expect(page.getByTestId("grid-column-cumulative_quantity")).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-side")).toHaveText("bid")

  await openNode(page, "Candles")
  await openNode(page, "1h")
  await expect(page.getByTestId("grid-column-open_time")).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-closed")).toBeVisible()

  await deleteConnector(page, name)
})

/**
 * A symbol's trades read on by a pipeline's link into a table it makes, keyed
 * by the trade id, the bookmark kept by DataPlayer (D319).
 */
test("reads a symbol's trades into a table its link makes, each trade once", async ({ page }) => {
  const stamp = Date.now()
  const name = `e2e-binance-pipe-${stamp}`
  const database = `e2e-binance-db-${stamp}`
  const table = `e2e_trades_${stamp}`
  await login(page)
  const api = await signedApi(page)
  await binanceConnection(page, api, name)
  await createPostgresConnector(page, database)

  await page.getByTestId("space-pipelines").click()
  const first = page.getByTestId("pipeline-create-first")
  await expect(first.or(page.getByTestId("pipeline-new"))).toBeVisible()
  if (await first.isVisible()) await first.click()
  else await page.getByTestId("pipeline-new").click()
  await expect(page.getByTestId("pipeline-view")).toBeVisible()

  const rail = page.getByTestId("pipelines-rail")
  const picker = page.getByTestId("card-picker")
  await rail.getByTestId(`connector-${name}`).click()
  await picker.getByTestId("catalog-node-Spot").click()
  await picker.getByTestId("catalog-node-USDT").click()
  await picker.getByTestId("catalog-node-BTCUSDT").click()
  await picker.getByTestId("catalog-check-Trades").click()
  await picker.getByTestId("card-picker-done").click()
  await rail.getByTestId(`connector-${database}`).click()
  await picker.getByTestId("catalog-check-public").click()
  await picker.getByTestId("card-picker-done").click()

  await drawLink(page, canvasRow(page, "Trades"), canvasRow(page, "public"))
  const panel = page.getByTestId("link-panel")
  await expect(panel.getByTestId("link-panel-sentence")).toContainText("Add new messages to a new table")
  const window = page.getByTestId("grid-create-table-dialog")
  await expect(window).toBeVisible()
  await window.getByTestId("grid-create-table-name").fill(table)
  await window.getByTestId("grid-create-table-run").click()
  await expect(window).toHaveCount(0)

  // From now on: the last hour of BTCUSDT is over a hundred thousand trades.
  await page.getByTestId("link-panel-start").click()
  await page.getByRole("option", { name: "Only what is new", exact: true }).click()
  await page.getByTestId("pipeline-run").click()
  const result = panel.getByTestId("link-panel-result")
  await expect(result).toContainText("the table was made with a key on id", { timeout: 60_000 })
  await expect(panel.getByTestId("link-panel-reader")).toContainText("dataplayer-link-")
  await page.screenshot({ path: "test-results/binance-pipeline.png" })

  // BTCUSDT trades every second; the next run adds only what came since.
  await page.getByTestId("pipeline-run").click()
  await expect(result).toContainText("new messages added", { timeout: 60_000 })
  await expect(result).not.toContainText("the table was made")

  await page.getByTestId("pipeline-delete").click()
  await page.getByTestId("confirm-accept").click()
  await page.getByTestId("space-data").click()
  await deleteConnector(page, database)
  await deleteConnector(page, name)
})
