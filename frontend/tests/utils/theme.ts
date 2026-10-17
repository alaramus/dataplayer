import { expect } from "@playwright/test"
import type { APIRequestContext, Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "../config"

const api = `${process.env.VITE_API_URL ?? "http://localhost:8000"}/api/v1`

/**
 * Put a theme on an account (D224), or null for the system's. The theme is
 * the account's, so a scenario that leaves one behind would paint every
 * scenario after it; `login` starts each from the system's.
 */
export async function setAccountTheme(
  request: APIRequestContext,
  theme: string | null,
  email = firstSuperuser,
  password = firstSuperuserPassword
): Promise<void> {
  const signedIn = await request.post(`${api}/login/access-token`, {
    form: { username: email, password },
  })
  if (!signedIn.ok()) throw new Error(`Could not sign ${email} in: ${String(signedIn.status())}`)
  const { access_token: token } = (await signedIn.json()) as { access_token: string }
  const saved = await request.patch(`${api}/users/me/preferences`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { theme },
  })
  if (!saved.ok()) throw new Error(`Could not set the theme for ${email}: ${String(saved.status())}`)
}

/**
 * Choose the theme without leaving the scenario for the Preferences page: on
 * the account, then a reload to read it. The toggle itself, in its
 * Preferences home, is covered by theme.spec.
 */
export async function chooseTheme(page: Page, theme: string) {
  await setAccountTheme(page.request, theme)
  await page.reload()
  const dark = !["light", "paper-light"].includes(theme)
  await expect(page.locator("body.body--dark")).toHaveCount(dark ? 1 : 0)
}
