import { expect, test } from "@playwright/test"

import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"

for (const theme of ["light", "dark"] as const) {
  test(`dashboard sharing stays aligned and scrolls in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await page.route("**/api/v1/metrics/store", (route) => route.fulfill({ json: { state: "ready", may_set_up: true } }))
    await page.route("**/api/v1/metrics/dashboards", (route) => route.fulfill({ json: [{
      id: "layout-dashboard", name: "Layout dashboard", version: 1,
      updated_at: "2026-09-21T00:00:00Z", widgets: [], access: "own",
    }] }))
    await page.route("**/api/v1/users/directory", (route) => route.fulfill({ json: {
      data: [{ id: "recipient", email: "recipient@example.test", full_name: "Example recipient" }], count: 1,
    } }))
    let given = false
    await page.route("**/api/v1/metrics/dashboards/layout-dashboard/grants", async (route) => {
      if (route.request().method() === "PUT") {
        expect(route.request().postDataJSON()).toEqual({ user_id: "recipient", access: "read" })
        given = true
        await route.fulfill({ json: { user_id: "recipient", email: "recipient@example.test", access: "read" } })
      } else {
        await route.fulfill({ json: given ? Array.from({ length: 18 }, (_, i) => ({
          user_id: `recipient-${i}`, email: `recipient-${i}@example.test`, full_name: `Example recipient ${i}`, access: "read",
        })) : [] })
      }
    })
    await login(page)
    await page.getByTestId("space-dashboards").click()
    await page.getByTestId("dashboard-Layout dashboard").click()
    await page.getByTestId("dashboard-share").click()
    const dialog = page.getByTestId("dashboard-share-dialog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(dialog.getByText("Nobody else can see this dashboard")).toBeVisible()
    const before = await frame.boundingBox()
    await page.getByTestId("dashboard-share-user").click()
    await page.getByRole("option", { name: "Example recipient (recipient@example.test)", exact: true }).click()
    await expectFieldActionAligned(page.getByTestId("dashboard-share-level"), page.getByTestId("dashboard-share-submit"))
    await page.getByTestId("dashboard-share-submit").click()
    await expect(page.getByTestId("dashboard-grant-recipient-17@example.test")).toBeAttached()
    expect(await frame.boundingBox()).toEqual(before)
    await frame.screenshot({ path: `test-results/dashboard-share-${theme}.png` })
    await page.setViewportSize({ width: 390, height: 600 })
    await expect(async () => {
      await expectFieldActionAligned(page.getByTestId("dashboard-share-level"), page.getByTestId("dashboard-share-submit"))
    }).toPass({ timeout: 5000 })
    const body = dialog.locator(".window-dialog__content")
    await expect.poll(() => body.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("dashboard-share-close")).toBeInViewport()
    await frame.screenshot({ path: `test-results/dashboard-share-${theme}-narrow.png` })
    await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect(page.getByTestId("dashboard-grant-recipient-17@example.test")).toBeInViewport()
    await expect(page.getByTestId("dashboard-share-close")).toBeInViewport()
    await page.getByTestId("dashboard-share-close").click()
  })
}
