import { expect, test } from "@playwright/test"
import type { APIRequestContext, Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "./config"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

/**
 * The language of the interface (D224): the browser's until the account
 * chooses one, the account's after, in any browser it signs in from.
 */

const api = `${process.env.VITE_API_URL ?? "http://localhost:8000"}/api/v1`

/** Put the account back on the browser's language, whatever a scenario left. */
async function forgetLanguage(request: APIRequestContext) {
  await setLanguage(request, null)
}

async function setLanguage(request: APIRequestContext, language: "ru" | null) {
  const signedIn = await request.post(`${api}/login/access-token`, {
    form: { username: firstSuperuser, password: firstSuperuserPassword },
  })
  const { access_token: token } = (await signedIn.json()) as { access_token: string }
  const saved = await request.patch(`${api}/users/me/preferences`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { language },
  })
  expect(saved.ok()).toBe(true)
}

async function chooseLanguage(page: Page, name: string) {
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/users/me/preferences")
  )
  await page.getByTestId("preference-language").click()
  // An option's name carries its second line, so it is matched by its start.
  await page.getByRole("option", { name: new RegExp(`^${name}`) }).click()
  await saved
}

test.afterEach(async ({ request }) => {
  await forgetLanguage(request)
})

test.describe("a browser asking for Russian", () => {
  test.use({ locale: "ru-RU" })

  test("is answered in Russian before anybody signs in", async ({ page }) => {
    await page.goto("/login")

    await expect(page.locator("html")).toHaveAttribute("lang", "ru")
    await expect(page.getByTestId("login-email")).toHaveAccessibleName("Эл. почта")
    await page.getByTestId("login-submit").click()
    await expect(page.getByText("Укажите пароль", { exact: true })).toBeVisible()
  })
})

test("an account's language is kept by the server and follows it", async ({ page, browser }) => {
  await login(page)
  await page.goto("/preferences/general")
  await expect(page.getByRole("heading", { name: "Preferences" })).toBeVisible()

  await chooseLanguage(page, "Русский")
  await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible()
  await expect(page.getByTestId("preferences-section-connections")).toContainText("Подключения")

  // Another browser, English by its own wish: the account's choice wins once
  // it is signed in.
  const elsewhere = await browser.newPage({ locale: "en-US" })
  try {
    await login(elsewhere)
    await elsewhere.goto("/preferences/general")
    await expect(elsewhere.getByRole("heading", { name: "Настройки" })).toBeVisible()
  } finally {
    await elsewhere.close()
  }

  // No language at all is the browser's, and this one is English.
  await chooseLanguage(page, "Язык браузера")
  await expect(page.getByRole("heading", { name: "Preferences" })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: "Preferences" })).toBeVisible()
})

test("what a source writes reaches a Russian reader in Russian", async ({ page, request }) => {
  const name = `e2e-words-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  // The title is the adapter's, worded by the server in the language the
  // interface names (D226) — not in the browser's dictionaries.
  await setLanguage(request, "ru")
  await page.reload()
  await openConnector(page, name)
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-create_schema")).toContainText("Новая схема")
  await page.keyboard.press("Escape")

  await setLanguage(request, null)
  await page.reload()
  await deleteConnector(page, name)
})

