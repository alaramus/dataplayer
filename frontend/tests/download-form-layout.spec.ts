import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { dismissToast } from "./utils/notices"
import { deleteConnector, openConnector } from "./utils/workspace"

async function openDownload(page: Page, name: string) {
  await createPostgresConnector(page, name)
  await dismissToast(page, "Connection saved")
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await page.getByTestId("grid-download").click()
  const content = page.getByTestId("grid-download-dialog")
  await expect(content).toBeVisible()
  return { content, frame: page.getByRole("dialog").filter({ has: content }) }
}

for (const theme of ["light", "dark"] as const) {
  test(`download form offers its two scopes as one labelled choice in ${theme}`, async ({ page }) => {
    const name = `e2e-download-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    try {
      const { content, frame } = await openDownload(page, name)
      const scopes = frame.getByRole("radiogroup", { name: "Rows", exact: true })
      await expect(scopes).toBeVisible()
      const pageScope = scopes.getByRole("radio", { name: "Current page", exact: true })
      const allScope = scopes.getByRole("radio", { name: "All matching rows", exact: true })
      await expect(pageScope).toHaveAttribute("aria-checked", "true")
      await expect(pageScope).toHaveAccessibleDescription(/visible columns/)
      await expect(allScope).toHaveAccessibleDescription(/The whole relation · streamed/)

      // The only question in the window has no label column to leave empty:
      // its choices start where the subtitle does.
      await expect(frame.getByText("Rows", { exact: true })).toHaveCount(0)
      const subtitle = await content.locator(".window-dialog__subtitle").evaluate((el) =>
        el.getBoundingClientRect().x + parseFloat(getComputedStyle(el).paddingLeft))
      const first = await pageScope.boundingBox()
      if (!first) throw new Error("Missing choice")
      expect(Math.abs(first.x - subtitle)).toBeLessThan(4)

      const before = await frame.boundingBox()
      await page.getByTestId("download-scope-all").click()
      await expect(allScope).toHaveAttribute("aria-checked", "true")
      await expect(pageScope).toHaveAttribute("aria-checked", "false")
      expect(await frame.boundingBox()).toEqual(before)
      await expect(frame.getByRole("button", { name: "Download", exact: true })).toBeVisible()
      const body = content.locator(".window-dialog__content")
      expect(await body.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
      await frame.screenshot({ path: `test-results/download-form-${theme}.png` })

      await page.setViewportSize({ width: 390, height: 600 })
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("grid-download-run")).toBeInViewport()
      await frame.screenshot({ path: `test-results/download-form-${theme}-narrow.png` })
      await frame.getByRole("button", { name: "Cancel", exact: true }).click()
      await expect(content).toHaveCount(0)
    } finally {
      await page.setViewportSize({ width: 1280, height: 720 })
      await deleteConnector(page, name)
    }
  })
}
