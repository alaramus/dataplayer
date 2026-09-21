import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, showOnlySchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { dismissToast } from "./utils/notices"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`generic actions keep one stable form in ${theme}`, async ({ page }) => {
    const name = `e2e-action-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createFileConnector(page, name)
    await dismissToast(page, "Connection saved")

    try {
      await openConnector(page, name)

      await catalogAction(page, "create_folder")
      const simpleContent = page.getByTestId("action-dialog")
      const simpleFrame = page.getByRole("dialog").filter({ has: simpleContent })
      await expect.poll(async () => (await simpleFrame.boundingBox())?.height ?? 999).toBeLessThan(300)
      await simpleFrame.screenshot({
        path: `test-results/action-dialog-simple-${theme}.png`,
        animations: "disabled",
      })
      await simpleFrame.getByRole("button", { name: "Cancel", exact: true }).click()

      await catalogAction(page, "upload")

      const content = page.getByTestId("action-dialog")
      const frame = page.getByRole("dialog").filter({ has: content })
      const before = await frame.boundingBox()

      await page.getByTestId("action-file").setInputFiles([
        { name: "first.csv", mimeType: "text/csv", buffer: Buffer.from("id\n1\n") },
        { name: "second.csv", mimeType: "text/csv", buffer: Buffer.from("id\n2\n") },
        { name: "third.csv", mimeType: "text/csv", buffer: Buffer.from("id\n3\n") },
      ])
      await expect(page.getByTestId("action-files")).toContainText("third.csv")
      expect(await frame.boundingBox()).toEqual(before)

      await page.getByTestId("action-file-remove-1").click()
      await expect(page.getByTestId("action-files")).not.toContainText("second.csv")
      expect(await frame.boundingBox()).toEqual(before)
      await page.mouse.move(450, 300)
      await frame.screenshot({
        path: `test-results/action-dialog-${theme}.png`,
        animations: "disabled",
      })

      await page.setViewportSize({ width: 390, height: 520 })
      await expect.poll(async () => {
        const box = await frame.boundingBox()
        return box !== null && box.x >= 0 && box.y >= 0 && box.x + box.width <= 390
      }).toBe(true)
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(frame.getByRole("button", { name: "Cancel", exact: true })).toBeInViewport()
      await expect(page.getByTestId("action-submit")).toBeInViewport()
      await frame.screenshot({
        path: `test-results/action-dialog-${theme}-narrow.png`,
        animations: "disabled",
      })
      await frame.getByRole("button", { name: "Cancel", exact: true }).click()
    } finally {
      await deleteConnector(page, name)
    }
  })

  test(`preview actions use a compact stable form in ${theme}`, async ({ page }) => {
    const name = `e2e-action-preview-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await dismissToast(page, "Connection saved")

    try {
      await openConnector(page, name)
      await showOnlySchema(page, "demo_lab")
      await catalogCheck(page, "projects").click()
      await catalogAction(page, "drop_relation")

      const content = page.getByTestId("action-dialog")
      const frame = page.getByRole("dialog").filter({ has: content })
      await expect(page.getByTestId("action-preview")).toBeVisible()
      await expect.poll(async () => (await frame.boundingBox())?.height).toBe(360)
      await frame.screenshot({
        path: `test-results/action-dialog-preview-${theme}.png`,
        animations: "disabled",
      })
      await frame.getByRole("button", { name: "Cancel", exact: true }).click()
    } finally {
      await deleteConnector(page, name)
    }
  })
}
