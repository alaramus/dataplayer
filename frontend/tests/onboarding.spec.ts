import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "./config"
import { setTourSeen } from "./utils/onboarding"

/**
 * The first-visit welcome tour.
 *
 * Every other scenario signs in through `utils/login`, which arrives with
 * the tour already seen. This one marks it unseen on the account first, to
 * meet the tour as a first-time visitor does.
 */
async function loginFresh(page: Page) {
  await setTourSeen(page.request, firstSuperuser, firstSuperuserPassword, false)
  await page.goto("/login")
  await page.getByTestId("login-email").fill(firstSuperuser)
  await page.getByTestId("login-password").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}

test("a first visit opens the welcome tour, and skipping it keeps it closed", async ({
  page,
}) => {
  await loginFresh(page)

  // The welcome opens over the fresh workspace, starting at the theme choice.
  await expect(page.getByTestId("onboarding-dialog")).toBeVisible()
  await expect(page.getByTestId("onboarding-theme")).toBeVisible()
  await page.getByTestId("onboarding-primary").click()

  // The tour itself: the first clip, then one step forward.
  await expect(page.getByTestId("onboarding-video")).toBeVisible()
  await expect(page.getByTestId("onboarding-position")).toHaveText("Step 1 of 6")
  await page.getByTestId("onboarding-primary").click()
  await expect(page.getByTestId("onboarding-position")).toHaveText("Step 2 of 6")

  // Skipping closes it, and a reload does not bring it back.
  await page.getByTestId("onboarding-skip").click()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)
})

test("the welcome offers the language first, and the rest of it follows the choice", async ({
  page,
}) => {
  await loginFresh(page)
  const welcome = page.getByTestId("onboarding-dialog")
  await expect(page.getByTestId("onboarding-language")).toBeVisible()
  await expect(welcome).toContainText("Pick a language")

  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/users/me/preferences")
  )
  await page.getByTestId("onboarding-language-ru").click()
  await saved
  // The account keeps it (D224), and the welcome is read in it at once.
  await expect(welcome).toContainText("Выберите язык")

  // Back to the browser's language, so every other scenario reads English.
  await page.getByTestId("onboarding-language-browser").click()
  await expect(welcome).toContainText("Pick a language")
  await page.getByTestId("onboarding-skip").click()
  await expect(welcome).toHaveCount(0)
})

test("Preferences replays the tour from its first clip", async ({ page }) => {
  await loginFresh(page)
  await expect(page.getByTestId("onboarding-dialog")).toBeVisible()
  await page.getByTestId("onboarding-skip").click()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)

  await page.goto("/preferences")
  await page.getByTestId("preference-replay-tour").click()
  await expect(page.getByTestId("onboarding-video")).toBeVisible()
  await expect(page.getByTestId("onboarding-position")).toHaveText("Step 1 of 6")
})
