import { expect, test } from "@playwright/test"

import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { catalogTab, deleteConnector, openConnector } from "./utils/workspace"

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

/** Choose a theme where it is chosen: Preferences, next to the account. */
async function choose(page: Page, theme: "Light" | "Dark" | "System") {
  await page.getByTestId("user-menu").click()
  await page.getByTestId("menu-item-preferences").click()
  await page.waitForURL("/preferences")
  await page.getByTestId("preference-theme").click()
  await page.getByRole("option", { name: theme }).click()
  await expect(page.getByTestId("preference-theme")).toContainText(theme)
}

async function backToWorkspace(page: Page) {
  await page.getByTestId("back-to-workspace").click()
  await page.waitForURL("/")
}

test("a chosen theme outlives a reload and outranks the system", async ({ page }) => {
  await login(page)

  // The system says dark, so choosing light is a choice that has to survive
  // being asked again — and the store asks the system only while System is
  // what is chosen.
  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  const wasDark = await panelColour(page)
  await choose(page, "Light")
  await expect(dark(page)).toHaveCount(0)
  await backToWorkspace(page)

  const wasLight = await panelColour(page)
  expect(wasLight).not.toBe(wasDark)
  // Painted, not merely re-declared: a variable nothing reads changes nothing.
  expect(wasLight).toBe("rgb(255, 255, 255)")

  await page.reload()
  await expect(dark(page)).toHaveCount(0)
  expect(await panelColour(page)).toBe(wasLight)

  // And back, so neither direction is the one that happens to work.
  await choose(page, "Dark")
  await expect(dark(page)).toHaveCount(1)
  await backToWorkspace(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)
  expect(await panelColour(page)).toBe(wasDark)
})

test("System follows the operating system while the page is open", async ({ page }) => {
  await login(page)
  await page.emulateMedia({ colorScheme: "light" })
  await forget(page)
  await page.reload()

  await choose(page, "Dark")
  await expect(dark(page)).toHaveCount(1)

  // Chosen back, the answer is the system's — and it keeps being the
  // system's when that changes without a reload.
  await choose(page, "System")
  await expect(dark(page)).toHaveCount(0)
  await page.emulateMedia({ colorScheme: "dark" })
  await expect(dark(page)).toHaveCount(1)
  await page.emulateMedia({ colorScheme: "light" })
  await expect(dark(page)).toHaveCount(0)
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

  // The grid paints its own surface to match the panel and sticky heading,
  // including when a floating window supplies a different background.
  const panel = await colourOf('[data-testid^="workspace-leaf-"]')
  expect(await colourOf('[data-testid="row-grid"]')).toBe(panel)
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
  // A console rather than the DDL of a relation: an editor that is not
  // editable hands the selection to the browser and paints no layer of its
  // own, so it could not answer what CodeMirror paints.
  await openConnector(page, name)
  await page.getByTestId("command-queries").click()
  await page.getByTestId("new-query").click()
  const editor = page.locator(".cm-content")
  await editor.click()
  await page.keyboard.type("select 'selected'")
  await expect(editor).toContainText("selected")

  await page.keyboard.press("ControlOrMeta+a")
  const painted = page.locator(".cm-selectionBackground").first()
  await expect(painted).toBeVisible()
  expect(await painted.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(
    "rgba(100, 181, 246, 0.4)"
  )

  await deleteConnector(page, name)
})

test("the editor's own tooltips and panels take the dark theme", async ({
  page,
}) => {
  // What CodeMirror draws around the text — the list of completions, the
  // search bar — is painted by its base theme, and that theme is the light
  // one here because nothing tells it otherwise. The completions came out
  // near-white under text this application had already made near-white: the
  // words were there and could not be read. Only the cascade can say whether
  // they can be, so it is asked where the cascade is real.
  const name = `e2e-completion-${Date.now()}`
  await login(page)
  await page.emulateMedia({ colorScheme: "dark" })
  await forget(page)
  await page.reload()
  await expect(dark(page)).toHaveCount(1)

  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await page.getByTestId("command-queries").click()
  await page.getByTestId("queries-connector").click()
  await page.getByRole("option", { name, exact: true }).click()
  await page.getByTestId("new-query").click()
  await page.locator(".cm-content").click()
  await page.keyboard.type("a")

  const offered = page.locator(".cm-tooltip-autocomplete")
  await expect(offered).toBeVisible()
  await expect(offered).toHaveCSS("background-color", "rgb(25, 25, 25)")

  // Every word in the same colour the rest of the application writes in, and
  // the row under the caret on this application's own selection tint rather
  // than the white-on-blue the base theme reaches for.
  const chosen = offered.getByRole("option", { selected: true })
  await expect(chosen).toHaveCSS("color", "rgba(255, 255, 255, 0.87)")
  await expect(chosen).toHaveCSS("background-color", "rgba(100, 181, 246, 0.18)")
  await expect(offered.getByRole("option").last()).toHaveCSS(
    "color",
    "rgba(255, 255, 255, 0.87)"
  )

  // The search bar, on the ground the gutters stand on, with a field and a
  // button that belong to it. The button is the one that cannot be fixed by a
  // colour: what the base theme gives it is a grey gradient.
  await page.keyboard.press("Escape")
  await page.keyboard.press("ControlOrMeta+f")
  const panel = page.locator(".cm-panels")
  await expect(panel).toBeVisible()
  await expect(panel).toHaveCSS("background-color", "rgb(43, 43, 43)")
  await expect(panel.getByRole("textbox", { name: "Find" })).toHaveCSS(
    "background-color",
    "rgb(18, 18, 18)"
  )
  const next = panel.getByRole("button", { name: "next", exact: true })
  await expect(next).toHaveCSS("background-color", "rgb(18, 18, 18)")
  await expect(next).toHaveCSS("background-image", "none")

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
  // black on near-black while every unit test stayed green. A catalog of a
  // connection nobody gave a colour; the connections have a head rather than
  // a tab.
  const name = `e2e-dark-tab-${Date.now()}`
  await createFileConnector(page, name)
  await openConnector(page, name)
  const tab = catalogTab(page)
  await expect(tab).toBeVisible()
  expect(await tab.evaluate((node) => getComputedStyle(node).color)).toBe("rgb(255, 255, 255)")

  await deleteConnector(page, name)
})
