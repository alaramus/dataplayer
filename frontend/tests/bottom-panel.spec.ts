import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

/**
 * The panel at the foot of the workspace (D143).
 *
 * Where a card is drawn, and whether it outlives a change of space and a
 * reload, are questions about the layout and the browser, so they are asked
 * here rather than of the functions behind them.
 */
test("services open in the panel at the foot of the screen, running or not", async ({ page }) => {
  // Nothing running, whatever the development server has left behind: the
  // button opens all the same, and the panel says there is nothing.
  await page.route("**/api/v1/services/", async (route) => {
    if (route.request().method() === "GET") await route.fulfill({ json: [] })
    else await route.continue()
  })
  await login(page)

  const button = page.getByTestId("command-services")
  const panel = page.getByTestId("bottom-panel")
  await expect(button).toBeEnabled()
  await expect(panel).toHaveCount(0)

  await button.click()
  await expect(panel).toBeVisible()
  await expect(panel).toContainText("Services")
  await expect(panel).toContainText("This server is not running anything for you")
  await expect(button).toHaveAttribute("aria-pressed", "true")

  // Under the columns rather than over them, and above the status bar.
  const columns = (await page.getByTestId("workspace").boundingBox())!
  const card = (await panel.boundingBox())!
  const footer = (await page.getByTestId("app-footer").boundingBox())!
  expect(columns.y + columns.height).toBeLessThanOrEqual(card.y)
  expect(card.y + card.height).toBeLessThanOrEqual(footer.y)

  // It stays where it is while the space above it changes.
  await page.getByTestId("space-dashboards").click()
  await expect(page.getByTestId("dashboards-space")).toBeVisible()
  await expect(panel).toBeVisible()
  await page.getByTestId("space-data").click()

  // The rail button is the tool's own switch, and the head can put it away too.
  await button.click()
  await expect(panel).toHaveCount(0)
  await expect(button).toHaveAttribute("aria-pressed", "false")
  await button.click()
  await expect(panel).toBeVisible()
  await page.getByTestId("bottom-panel-hide").click()
  await expect(panel).toHaveCount(0)

  // What was left open is what a reload finds.
  await button.click()
  await expect(panel).toBeVisible()
  await page.reload()
  await expect(panel).toBeVisible()
  await expect(panel).toContainText("This server is not running anything for you")
})
