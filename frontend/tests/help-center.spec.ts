import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

/**
 * The Help Center (D183): the whole guide from the user menu or F1, its
 * contents on the left and a search over every page.
 */
test("opens from the user menu, walks its contents and finds words in any page", async ({ page }) => {
  await login(page)
  await page.getByTestId("user-menu").click()
  const line = page.getByTestId("menu-item-help")
  await expect(line.locator("kbd")).toHaveText("F1")
  await line.click()

  const guide = page.getByTestId("guide-window")
  const text = guide.getByTestId("guide-text")
  const contents = guide.getByTestId("guide-contents")
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("DataPlayer at a glance")
  await expect(contents.getByTestId("guide-page-overview")).toHaveAttribute("aria-current", "page")

  // A page of the contents turns the window, and opens onto its headings.
  await contents.getByTestId("guide-page-source-redis").click()
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("Redis")
  await contents.getByTestId("guide-heading-connecting").click()
  await expect(text.getByRole("heading", { name: "Connecting" })).toBeFocused()

  // Words list the pages they are in, in place of the contents.
  await guide.getByTestId("guide-search").fill("hypertable")
  const found = contents.getByTestId("guide-found-source-postgres")
  await expect(found).toBeVisible()
  await found.click()
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("PostgreSQL")

  await guide.getByTestId("guide-search").fill("zzqqxx")
  await expect(contents.getByTestId("guide-nothing-found")).toBeVisible()
})

test("F1 opens the Help Center, and the empty scene lists it beside the search", async ({ page }) => {
  await login(page)
  await expect(page.getByTestId("scene-keys")).toContainText("F1")
  await expect(page.getByTestId("scene-keys")).toContainText("Open the Help Center")

  await page.locator("body").press("F1")
  await expect(page.getByTestId("guide-window")).toBeVisible()
})
