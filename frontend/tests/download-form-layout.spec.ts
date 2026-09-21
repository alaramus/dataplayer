import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

async function openDownload(page: Page, name: string) {
  await createPostgresConnector(page, name)
  await page.getByTestId("toast").filter({ hasText: "Connection saved" })
    .getByRole("button", { name: "Dismiss", exact: true }).click()
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

      // The group's label takes the label column, and the choices the control one.
      const label = await frame.getByText("Rows", { exact: true }).boundingBox()
      const first = await pageScope.boundingBox()
      const choice = await pageScope.getByText("Current page", { exact: true }).boundingBox()
      if (!label || !first || !choice) throw new Error("Missing scope label or choice")
      expect(label.x + label.width).toBeLessThan(first.x)
      // The label reads on the line of the first choice's name.
      expect(Math.abs(label.y + label.height / 2 - (choice.y + choice.height / 2))).toBeLessThan(2)

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
      await expect.poll(async () => {
        const narrowLabel = await frame.getByText("Rows", { exact: true }).boundingBox()
        const narrowFirst = await pageScope.boundingBox()
        return narrowLabel && narrowFirst ? narrowFirst.y - narrowLabel.y - narrowLabel.height : -1
      }).toBeGreaterThanOrEqual(0)
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
