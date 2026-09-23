import { expect, test } from "@playwright/test"

import { pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"

for (const theme of ["light", "dark"] as const) {
  test(`connection results keep the form and footer usable in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await pickAdapterType(page, "postgres")
    const frame = page.getByRole("dialog", { name: "New connection", exact: true })
    const result = page.getByRole("region", { name: "Connection check result", exact: true })
    for (const narrow of [false, true]) {
      if (narrow) {
        await page.setViewportSize({ width: 390, height: 600 })
        await expect.poll(async () => {
          const box = await frame.boundingBox()
          return box !== null && box.x >= 0 && box.y >= 0 &&
            box.x + box.width <= 390 && box.y + box.height <= 600
        }).toBe(true)
      }
      for (const ok of [true, false]) {
        await page.route("**/api/v1/connectors/check-draft", (route) => route.fulfill({ json: {
          ok,
          message: ok ? "Connection successful" : "The server could not be reached. ".repeat(40),
          error_kind: ok ? null : "network",
          latency_ms: 12,
          features: ok ? { observed_at: "2026-09-20T12:00:00Z", server_version: "17.6", features: [] } : null,
        } }))
        const before = await frame.boundingBox()
        await page.getByTestId("check-draft").click()
        await expect(result).toBeVisible()
        await expect(result.getByRole("status")).toHaveText(ok ? "Succeeded" : "Failed")
        await expect.poll(() => frame.boundingBox()).toEqual(before)
        const panel = await result.boundingBox()
        const button = await page.getByTestId("check-draft").boundingBox()
        if (!panel || !button) throw new Error("Missing connection result popup")
        expect(panel.x).toBeGreaterThanOrEqual(0)
        expect(panel.y).toBeGreaterThanOrEqual(0)
        expect(panel.x + panel.width).toBeLessThanOrEqual(narrow ? 390 : 1280)
        expect(panel.y + panel.height).toBeLessThanOrEqual(narrow ? 600 : 720)
        expect(Math.abs(panel.x - button.x)).toBeLessThan(30)
        expect(panel.y + panel.height).toBeLessThanOrEqual(button.y)
        await expect(page.getByTestId("cancel-connector")).toBeInViewport()
        const details = result.getByLabel("Check details")
        expect(await details.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
        if (!ok) {
          expect(await details.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
          await details.focus()
          await page.keyboard.press("End")
          await expect.poll(() => details.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
        }
        await page.keyboard.press("Escape")
        await expect(result).toHaveCount(0)
        await expect.poll(() => frame.boundingBox()).toEqual(before)
        await page.unroute("**/api/v1/connectors/check-draft")
      }
    }
  })
}
