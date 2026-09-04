import { expect } from "@playwright/test"
import type { Page } from "@playwright/test"

/**
 * A second person, and moving between the two of them.
 *
 * Anything about sharing needs two accounts and two sessions, so this lives
 * beside the scenarios rather than inside one of them.
 */
export const COLLEAGUE_PASSWORD = "shared-access-1"

export function colleagueEmail(): string {
  return `colleague-${Date.now()}@example.com`
}

export async function signInAs(page: Page, email: string, password: string) {
  await page.goto("/login")
  await page.getByTestId("login-email").fill(email)
  await page.getByTestId("login-password").fill(password)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}

export async function signOut(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByTestId("menu-item-logout").click()
  await page.waitForURL("/login")
}

export async function openAdmin(page: Page) {
  await page.getByTestId("user-menu").click()
  await page.getByTestId("menu-item-admin").click()
  await page.waitForURL("/admin")
}

export async function createColleague(page: Page, email: string) {
  await openAdmin(page)
  await page.getByTestId("new-user").click()
  await page.getByTestId("user-email").fill(email)
  await page.getByTestId("user-password").fill(COLLEAGUE_PASSWORD)
  await page.getByTestId("user-save").click()
  await expect(page.getByTestId(`edit-user-${email}`)).toBeVisible()
  await page.getByTestId("back-to-workspace").click()
  await page.waitForURL("/")
}

export async function removeColleague(page: Page, email: string) {
  await openAdmin(page)
  await page.getByTestId(`delete-user-${email}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId(`edit-user-${email}`)).toHaveCount(0)
}
