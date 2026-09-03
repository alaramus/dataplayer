import { expect, test } from "@playwright/test"

import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

/**
 * Light and dark, and where each of them comes from.
 *
 * None of this is provable without a browser: what a colour resolves to is a
 * question about the cascade, and whether a choice outlives a reload is a
 * question about what was written where.
 */

const dark = (page: Page) => page.locator("body.body--dark")

/** What a panel of the workspace is actually painted, right now. */
async function panelColour(page: Page): Promise<string> {
  return await page
    .locator('[data-testid^="workspace-leaf-"]')
    .first()
    .evaluate((node) => getComputedStyle(node).backgroundColor)
}

async function forget(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("dataplayer-theme")
  })
}

test("takes the theme from the system until somebody chooses", async ({ page }) => {
  await login(page)

  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  await page.emulateMedia({ colorScheme: "light" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(0)
})

test("a chosen theme outlives a reload and outranks the system", async ({ page }) => {
  await login(page)

  // The system says dark, so choosing light is a choice that has to survive
  // being asked again — and the store asks the system only when nothing has
  // been chosen.
  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  const wasDark = await panelColour(page)
  await page.getByTestId("theme-toggle").click()
  await expect(dark(page)).toHaveCount(0)

  const wasLight = await panelColour(page)
  expect(wasLight).not.toBe(wasDark)
  // Painted, not merely re-declared: a variable nothing reads changes nothing.
  expect(wasLight).toBe("rgb(255, 255, 255)")

  await page.reload()
  await expect(dark(page)).toHaveCount(0)
  expect(await panelColour(page)).toBe(wasLight)

  // And back, so neither direction is the one that happens to work.
  await page.getByTestId("theme-toggle").click()
  await expect(dark(page)).toHaveCount(1)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)
  expect(await panelColour(page)).toBe(wasDark)
})

test("a column of the workspace is one colour, grid included", async ({ page }) => {
  const name = `e2e-theme-grid-${Date.now()}`
  await login(page)
  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("row-grid")).toContainText("relname")

  const colourOf = (selector: string) =>
    page.locator(selector).first().evaluate((node) => getComputedStyle(node).backgroundColor)

  // Cells are transparent over the panel and the grid heading spends the same
  // surface token, so the table does not become a raised card or a stripe.
  const panel = await colourOf('[data-testid^="workspace-leaf-"]')
  expect(await colourOf('[data-testid="row-grid"]')).toBe("rgba(0, 0, 0, 0)")
  expect(await colourOf('[data-testid="grid-column-relname"]')).toBe(panel)

  await deleteConnector(page, name)
})

test("selected text is readable in the dark theme", async ({ page }) => {
  // CodeMirror paints its own selection, five selectors deep, and the pale
  // lilac it uses by default swallows syntax colours on a near-black ground.
  // What it is painted with is a question about the cascade, so it is asked
  // where the cascade is real.
  const name = `e2e-selection-${Date.now()}`
  await login(page)
  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await page.getByTestId("grid-content").click()
  const editor = page.locator(".cm-content")
  await expect(editor).toContainText("CREATE TABLE")

  await editor.click()
  await page.keyboard.press("ControlOrMeta+a")
  const painted = page.locator(".cm-selectionBackground").first()
  await expect(painted).toBeVisible()
  expect(await painted.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(
    "rgba(100, 181, 246, 0.4)"
  )

  await deleteConnector(page, name)
})

test("a tab is legible in the dark theme", async ({ page }) => {
  await login(page)

  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  // A native <button> takes its colour from the browser, which is black, and
  // `font: inherit` does not carry colour with it — so the tab strip went
  // black on near-black while every unit test stayed green.
  const tab = page.getByTestId("workspace-tab-connectors")
  await expect(tab).toBeVisible()
  expect(await tab.evaluate((node) => getComputedStyle(node).color)).toBe("rgb(255, 255, 255)")
})
