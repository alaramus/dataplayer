import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"

export async function login(page: Page) {
  await page.goto("/login")
  // Quasar пробрасывает data-testid на сам input, поэтому идентификатор
  // адресует поле ввода напрямую.
  await page.getByTestId("login-email").fill(firstSuperuser)
  await page.getByTestId("login-password").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}
