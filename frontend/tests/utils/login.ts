import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"

export async function login(page: Page) {
  await page.goto("/login")
  // Quasar forwards data-testid onto the input itself, so the id addresses the
  // input element directly.
  await page.getByTestId("login-email").fill(firstSuperuser)
  await page.getByTestId("login-password").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}
