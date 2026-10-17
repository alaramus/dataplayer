import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"
import { setTourSeen } from "./onboarding"
import { setAccountTheme } from "./theme"

export async function login(page: Page) {
  // The first-visit tour opens over the workspace on a fresh profile and
  // would cover the controls under test. Every scenario except the tour's
  // own arrives with it already seen.
  await setTourSeen(page.request, firstSuperuser, firstSuperuserPassword)
  // The theme is the account's: whatever the scenario before chose would
  // otherwise paint this one.
  await setAccountTheme(page.request, null)
  await page.goto("/login")
  // Quasar forwards data-testid onto the input itself, so the id addresses the
  // input element directly.
  await page.getByTestId("login-email").fill(firstSuperuser)
  await page.getByTestId("login-password").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}
