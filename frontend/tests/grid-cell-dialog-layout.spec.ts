import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { openNode, pickSchema } from "./utils/catalog"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`cell viewer and editor keep their window composition in ${theme}`, async ({ page }) => {
    const name = `e2e-cell-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await page.getByTestId("toast").filter({ hasText: "Connection saved" })
      .getByRole("button", { name: "Dismiss", exact: true }).click()
    try {
      await openConnector(page, name)
      await pickSchema(page, "demo_lab")
      await openNode(page, "audit_events")

      await page.getByTestId("grid-cell-0-payload").dblclick()
      const viewer = page.getByRole("dialog").filter({ has: page.getByTestId("grid-viewer") })
      const viewerRect = await viewer.boundingBox()
      await expect(page.getByTestId("grid-viewer")).toContainText('"source"')
      await expect(page.getByTestId("grid-viewer-copy")).toBeVisible()
      expect(await viewer.boundingBox()).toEqual(viewerRect)
      await viewer.screenshot({ path: `test-results/grid-cell-viewer-${theme}.png`, animations: "disabled" })
      await viewer.getByRole("button", { name: "Close", exact: true }).click()

      await openNode(page, "projects")
      await page.getByTestId("grid-cell-0-budget").dblclick()
      const editorContent = page.getByTestId("grid-cell-editor")
      const editor = page.getByRole("dialog").filter({ has: editorContent })
      const editorRect = await editor.boundingBox()
      const value = page.getByTestId("grid-edit-value")
      const valueBox = await value.boundingBox()
      const labelBox = await editor.getByText("Value", { exact: true }).boundingBox()
      if (!valueBox || !labelBox) throw new Error("Missing editor field or label")
      expect(labelBox.x + labelBox.width).toBeLessThan(valueBox.x)
      expect(valueBox.height).toBeLessThanOrEqual(36)

      await page.route("**/api/v1/connectors/*/rows/cell", (route) => route.fulfill({
        status: 400,
        json: { detail: "This value cannot be stored in the selected column" },
      }))
      await page.getByTestId("grid-edit-save").click()
      await expect(page.getByTestId("grid-edit-error")).toContainText("cannot be stored")
      await expect(page.getByTestId("grid-edit-save")).toBeEnabled()
      expect(await editor.boundingBox()).toEqual(editorRect)
      await value.focus()
      await editor.screenshot({ path: `test-results/grid-cell-editor-${theme}.png`, animations: "disabled" })

      await page.setViewportSize({ width: 390, height: 500 })
      await expect.poll(async () => {
        const box = await editor.boundingBox()
        return box !== null && box.x >= 0 && box.y >= 0 && box.x + box.width <= 390
      }).toBe(true)
      await expect.poll(async () => {
        const label = await editor.getByText("Value", { exact: true }).boundingBox()
        const field = await value.boundingBox()
        return label && field ? field.y - label.y - label.height : -1
      }).toBeGreaterThanOrEqual(0)
      await expect.poll(() => editorContent.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeInViewport()
      await editor.screenshot({ path: `test-results/grid-cell-editor-${theme}-narrow.png`, animations: "disabled" })
      await editor.getByRole("button", { name: "Cancel", exact: true }).click()
    } finally {
      await deleteConnector(page, name)
    }
  })
}
