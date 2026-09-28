import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"

for (const theme of ["light", "dark"] as const) {
  test(`AI settings form and archive remain usable in ${theme}`, async ({ page }) => {
    await login(page)
    await chooseTheme(page, theme)
    await page.route(/\/api\/v1\/ai\/conversations\?archived=true/, (route) => route.fulfill({ json: {
      data: [
        { id: "layout-archived-1", title: "First archived chat" },
        { id: "layout-archived-2", title: "Second archived chat" },
      ],
      count: 2,
    } }))
    await page.getByTestId("space-ai").click()
    await page.getByTestId("ai-open-settings").click()
    const settings = page.getByTestId("ai-settings")
    await expect(settings).toBeVisible()
    await expect.poll(() => page.getByTestId("ai-model").evaluate((el) =>
      el.querySelector(".q-field")?.classList.contains("q-field--outlined") ?? false
    )).toBe(true)
    await expect(settings.locator(".app-form")).toHaveCount(2)
    await expect(page.getByTestId("ai-allow-all")).toBeVisible()
    const archived = settings.locator('[data-testid^="ai-archived-"]')
    await expect(archived).toHaveCount(2)
    await expect(archived.nth(1)).toHaveCSS("border-top-width", "1px")
    // A row of the archive has room for the ordinary buttons, not a cell's.
    const ordinary = await page.getByTestId("ai-new-chat").first().boundingBox()
    for (const button of ["ai-restore-layout-archived-1", "ai-delete-layout-archived-1"]) {
      expect((await page.getByTestId(button).boundingBox())?.height).toBe(ordinary?.height)
    }
    await page.screenshot({ path: `test-results/ai-settings-${theme}.png` })
    await page.setViewportSize({ width: 390, height: 720 })
    const railToggle = page.getByTestId("app-toggle-first-panel")
    if (await railToggle.getAttribute("aria-label") === "Hide first panel") await railToggle.click()
    await expect.poll(() => settings.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("ai-model")).toBeInViewport()
    await expect(page.getByTestId("ai-allow-all")).toBeInViewport()
    await expect(page.getByTestId("ai-restore-layout-archived-2")).toBeInViewport()
    await page.screenshot({ path: `test-results/ai-settings-${theme}-narrow.png` })
  })
}
