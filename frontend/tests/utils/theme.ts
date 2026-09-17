import { expect } from "@playwright/test"
import type { Page } from "@playwright/test"

/**
 * Choose the theme without leaving the scenario for the Preferences page.
 *
 * The choice lives in localStorage and is read when the application starts,
 * so writing it and reloading is the same choice arriving one start earlier.
 * The toggle itself, in its Preferences home, is covered by theme.spec.
 */
export async function chooseTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((value) => localStorage.setItem("dataplayer-theme", value), theme)
  await page.reload()
  await expect(page.locator("body.body--dark")).toHaveCount(theme === "dark" ? 1 : 0)
}
