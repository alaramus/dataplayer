import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"

/**
 * What an account chose for itself, on a page of its own.
 *
 * The one scenario worth a browser: a preference is kept by the server, so
 * the proof is that it is still there after a reload — which is exactly what
 * a unit test of the same screen cannot say.
 */

const CHECKS = "preference-connector-checks"
const DEFAULT_LABEL = "Every 15 seconds"

async function openPreferences(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByTestId("menu-item-preferences").click()
  await page.waitForURL("/preferences")
}

/** Choose one, and wait for the server to have taken it rather than for a toast. */
async function choose(page: Page, label: string) {
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/users/me/preferences")
  )
  await page.getByTestId(CHECKS).click()
  await page.getByRole("option", { name: label, exact: true }).click()
  await saved
}

/** What the menu says is on, which is where a select states its answer. */
async function expectChosen(page: Page, label: string) {
  await page.getByTestId(CHECKS).click()
  await expect(page.getByRole("option", { name: label, exact: true })).toHaveAttribute(
    "aria-selected",
    "true"
  )
  await page.keyboard.press("Escape")
}

test("keeps how often connections are checked", async ({ page }) => {
  await login(page)
  await openPreferences(page)
  await expect(page.getByTestId("preferences")).toBeVisible()
  for (const [testId, label] of [
    ["preference-theme", "Theme"],
    [CHECKS, "How often connections are checked"],
  ] as const) {
    const control = page.getByTestId(testId)
    const field = page.locator(".q-field").filter({ has: control }).first()
    await expect(field).toHaveClass(/q-field--outlined/)
    await expect(control).toHaveAttribute("aria-label", label)
  }

  await choose(page, "Every 5 minutes")

  // The server holds it and not this tab: a reload is what tells them apart.
  await page.reload()
  await expectChosen(page, "Every 5 minutes")

  // Back to the default, so a scenario about a dot still has one.
  await choose(page, DEFAULT_LABEL)
  await page.reload()
  await expectChosen(page, DEFAULT_LABEL)

  await page.getByTestId("back-to-workspace").click()
  await page.waitForURL("/")
})
