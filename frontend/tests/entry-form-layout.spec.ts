import { expect, test } from "@playwright/test"
import type { Locator } from "@playwright/test"

async function expectOutlinedFormField(field: Locator) {
  await expect.poll(() => field.evaluate((el) =>
    el.closest(".q-field")?.classList.contains("q-field--outlined") ?? false
  )).toBe(true)
}

for (const theme of ["light", "dark"] as const) {
  test(`sign-in and server-link forms use compact fields in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await page.route("**/api/v1/utils/server-info", (route) => route.fulfill({ json: {
      product: "dataplayer",
      client_api_version: 1,
    } }))
    await page.goto("/login?next=%2Fdashboards%2Fexample")

    const email = page.getByTestId("login-email")
    const password = page.getByTestId("login-password")
    const submit = page.getByTestId("login-submit")
    await expect(email).toBeVisible()
    await expect(password).toBeVisible()
    await expect(submit).toBeEnabled()
    await expect(page.locator("q-layout, .q-layout, .q-page-container, .q-page")).toHaveCount(0)
    await expectOutlinedFormField(email)
    await expectOutlinedFormField(password)
    await expect(page.getByText("Email", { exact: true })).toBeVisible()
    await expect(page.getByText("Password", { exact: true })).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/sign-in-${theme}-wide.png` })

    await page.setViewportSize({ width: 390, height: 720 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(email).toBeVisible()
    await expect(password).toBeVisible()
    await expect(submit).toBeInViewport()
    await page.screenshot({ path: `test-results/sign-in-${theme}-narrow.png` })

    await page.goto(`/connect-server?server=${encodeURIComponent("https://link-server.example/player")}`)
    const serverUrl = page.getByTestId("link-server-url")
    const serverName = page.getByLabel("Server name")
    await expect(serverUrl).toHaveValue("https://link-server.example/player")
    await expectOutlinedFormField(serverName)
    await expectOutlinedFormField(serverUrl)
    await expect(page.getByTestId("link-server-connect")).toBeVisible()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `test-results/server-link-${theme}-narrow.png` })
  })
}
