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
      if (narrow) await page.setViewportSize({ width: 390, height: 600 })
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
        expect(await frame.boundingBox()).toEqual(before)
        const panel = await result.boundingBox()
        const url = await page.getByTestId("connector-url").boundingBox()
        const button = await page.getByTestId("check-draft").boundingBox()
        if (!panel || !url || !button) throw new Error("Missing connection layout")
        expect(panel.y).toBeGreaterThanOrEqual(url.y + url.height)
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
        await frame.screenshot({ path: `test-results/connection-result-${theme}-${narrow ? "narrow" : "wide"}-${ok ? "success" : "error"}.png` })
        await page.getByTestId("dismiss-check-result").click()
        await expect(result).toHaveCount(0)
        expect(await frame.boundingBox()).toEqual(before)
        await page.unroute("**/api/v1/connectors/check-draft")
      }
    }
  })
}
