import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { openNode, pickSchema } from "./utils/catalog"
import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`sharing form keeps its geometry and reflows in ${theme}`, async ({ page }) => {
    const name = `e2e-share-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await page.getByTestId("toast").filter({ hasText: "Connection saved" })
      .getByRole("button", { name: "Dismiss", exact: true }).click()
    await openConnector(page, name)
    await pickSchema(page, "demo_lab")
    await openNode(page, "tags")
    let failed = true
    await page.route("**/api/v1/users/directory", (route) => route.fulfill(failed
      ? { status: 400, json: { detail: "Directory unavailable" } }
      : { json: { data: [{ id: "layout-recipient", email: "recipient@example.test", full_name: "Example recipient" }], count: 1 } }))
    await page.route("**/api/v1/shares/?*", (route) => route.fulfill({ json: {
      data: Array.from({ length: 18 }, (_, i) => ({
        id: `layout-link-${i}`, token: `layout-token-${i}`, node_label: `Example view ${i + 1}`,
        shared_by: "owner@example.test", openers: [], can_delete: false,
      })), count: 18,
    } }))
    try {
      await page.getByTestId("grid-share").click()
      const content = page.getByTestId("share-dialog")
      const frame = page.getByRole("dialog").filter({ has: content })
      await expect(page.getByTestId("share-recipients-error")).toBeVisible()
      await expect(page.getByTestId("share-link")).toHaveValue(/\/s\//)
      const before = await frame.boundingBox()
      await expect(page.getByTestId("share-submit")).toBeDisabled()
      failed = false
      await frame.getByRole("button", { name: "Retry", exact: true }).click()
      await expect(page.getByTestId("share-recipients-error")).toHaveCount(0)
      await page.getByTestId("share-user").click()
      await page.getByRole("option", { name: "Example recipient (recipient@example.test)", exact: true }).click()
      await expect(page.getByRole("listbox")).toHaveCount(0)
      await expect(page.getByTestId("share-submit")).toBeEnabled()
      expect(await frame.boundingBox()).toEqual(before)
      await expectFieldActionAligned(page.getByTestId("share-level"), page.getByTestId("share-submit"))
      await frame.screenshot({ path: `test-results/share-form-${theme}.png` })
      await page.setViewportSize({ width: 390, height: 600 })
      await expectFieldActionAligned(page.getByTestId("share-level"), page.getByTestId("share-submit"))
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("share-close")).toBeInViewport()
      const body = content.locator(".window-dialog__content")
      expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
      await frame.screenshot({ path: `test-results/share-form-${theme}-narrow.png` })
      await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
      await expect(page.getByTestId("share-link-layout-link-17")).toBeInViewport()
      await expect(page.getByTestId("share-close")).toBeInViewport()
      await page.getByTestId("share-close").click()
    } finally {
      await deleteConnector(page, name)
    }
  })
}
