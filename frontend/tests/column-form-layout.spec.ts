import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { openNode, pickSchema } from "./utils/catalog"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`column forms keep geometry and actions in ${theme}`, async ({ page }) => {
    const name = `e2e-column-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await page.getByTestId("toast").filter({ hasText: "Connection saved" })
      .getByRole("button", { name: "Dismiss", exact: true }).click()
    await openConnector(page, name)
    await pickSchema(page, "demo_lab")
    await openNode(page, "tags")
    await page.getByTestId("grid-structure").click()
    // Refuse mutations deterministically; these scenes must not change sample data.
    await page.route(/\/api\/v1\/connectors\/[^/]+\/columns(?:\/[^/]+)?$/, (route) =>
      route.fulfill({ status: 400, json: { detail: "The source refused this change. ".repeat(12) } }))
    try {
      for (const kind of ["rename", "default", "type", "nullability"] as const) {
        await page.getByTestId(`structure-${kind}-label`).click()
        const content = page.getByTestId(`structure-${kind}-dialog`)
        const frame = page.getByRole("dialog").filter({ has: content })
        await expect(content).toBeVisible()
        const before = await frame.boundingBox()
        if (kind === "rename") {
          await page.getByTestId("structure-rename-new-name").fill("other_label")
        }
        if (kind === "default") {
          await page.getByTestId("structure-default-value").fill("Example")
        }
        await frame.screenshot({ path: `test-results/column-${kind}-${theme}.png` })
        await page.getByTestId(`structure-${kind}-save`).click()
        const error = page.getByTestId(`structure-${kind}-error`)
        await expect(error).toContainText("The source refused")
        expect(await frame.boundingBox()).toEqual(before)
        expect(await error.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgba(0, 0, 0, 0)")
        await page.setViewportSize({ width: 390, height: 500 })
        await expect(page.getByTestId(`structure-${kind}-save`)).toBeInViewport()
        await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
        const body = content.locator(".window-dialog__content")
        expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
        await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
        await expect(frame.getByRole("button", { name: "Cancel", exact: true })).toBeInViewport()
        await frame.screenshot({ path: `test-results/column-${kind}-${theme}-narrow-error.png` })
        await frame.getByRole("button", { name: "Cancel", exact: true }).click()
        await page.setViewportSize({ width: 1280, height: 900 })
      }
    } finally {
      await deleteConnector(page, name)
    }
  })
}
