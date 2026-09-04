import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { signOut } from "./utils/people"

test("a token the server no longer accepts sends the user to the login page", async ({
  page,
}) => {
  await login(page)

  // What an expired token, a rotated signing key or a deleted user look like
  // from the browser: the token is still there, the server just says no.
  await page.evaluate(() => localStorage.setItem("access_token", "no-longer-valid"))
  await page.reload()

  // Promptly: retrying a rejected token only delays the inevitable, and a few
  // seconds of a half-working page is what makes it look broken.
  await page.waitForURL("/login", { timeout: 3000 })
  await expect(page.getByTestId("login-submit")).toBeVisible()
})

test("signing out in one tab signs out the other", async ({ page, context }) => {
  await login(page)

  const other = await context.newPage()
  await other.goto("/")
  await signOut(other)
  await other.close()

  // The token is gone from storage, but this tab still holds it in memory and
  // the server would still accept it: nothing fails, so nothing would ever
  // reveal the sign-out on its own.
  await page.waitForURL("/login")
  await expect(page.getByTestId("login-submit")).toBeVisible()
})

test("a signed out tab cannot walk back into the application", async ({
  page,
  context,
}) => {
  await login(page)

  const other = await context.newPage()
  await other.goto("/")
  await signOut(other)
  await other.close()

  await page.waitForURL("/login")
  await page.goto("/")

  await expect(page).toHaveURL(/\/login$/)
})
