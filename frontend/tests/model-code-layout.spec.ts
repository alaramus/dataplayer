import { expect, test } from "@playwright/test"

import { catalogAction, showOnlySchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`model code keeps one stable document window in ${theme}`, async ({ page }) => {
    const name = `e2e-model-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await page.getByTestId("toast").filter({ hasText: "Connection saved" })
      .getByRole("button", { name: "Dismiss", exact: true }).click()
    try {
      await openConnector(page, name)
      await showOnlySchema(page, "demo_lab")

      let dialect = "dbml"
      let first = true
      let releaseFirst = () => {}
      const held = new Promise<void>((resolve) => { releaseFirst = resolve })
      await page.route("**/api/v1/connectors/*/actions/describe_model/download", async (route) => {
        const body = route.request().postDataJSON() as { params: { dialect: string } }
        dialect = body.params.dialect
        if (first) {
          first = false
          await held
        }
        if (dialect === "django") {
          await route.fulfill({ status: 400, json: { detail: "That dialect is unavailable" } })
          return
        }
        await route.fulfill({ json: { download_url: "/api/v1/model-layout" } })
      })
      await page.route("**/api/v1/model-layout", (route) => route.fulfill({
        body: dialect === "dbml" ? "Table demo_lab.projects {\n  id integer\n}" : "declarative_base()",
        contentType: "text/plain",
        headers: { "content-disposition": "attachment; filename=model.txt" },
      }))

      await catalogAction(page, "describe_model")
      const content = page.getByTestId("model-code-dialog")
      const frame = page.getByRole("dialog").filter({ has: content })
      await expect(page.getByTestId("model-code-loading")).toBeVisible()
      const before = await frame.boundingBox()
      releaseFirst()
      await expect(page.getByTestId("model-code-text")).toContainText("Table demo_lab.projects")
      expect(await frame.boundingBox()).toEqual(before)
      await expect(page.getByRole("tab", { name: "DBML (dbdiagram.io)", exact: true })).toHaveAttribute("aria-selected", "true")

      await page.getByTestId("model-code-dialect-django").click()
      await expect(page.getByTestId("model-code-error")).toContainText("unavailable")
      expect(await frame.boundingBox()).toEqual(before)
      await expect(page.getByTestId("model-code-save")).toBeDisabled()

      await page.getByTestId("model-code-dialect-sqlalchemy").click()
      await expect(page.getByTestId("model-code-text")).toContainText("declarative_base")
      expect(await frame.boundingBox()).toEqual(before)
      await expect(page.getByTestId("model-code-save")).toBeEnabled()
      await page.getByRole("textbox", { name: "model.txt source" }).focus()
      await page.mouse.move(450, 300)
      await frame.screenshot({ path: `test-results/model-code-${theme}.png`, animations: "disabled" })

      await page.setViewportSize({ width: 390, height: 520 })
      await expect.poll(async () => {
        const box = await frame.boundingBox()
        return box !== null && box.x >= 0 && box.y >= 0 && box.x + box.width <= 390
      }).toBe(true)
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("model-code-close")).toBeInViewport()
      await expect(page.getByTestId("model-code-save")).toBeInViewport()
      await frame.screenshot({ path: `test-results/model-code-${theme}-narrow.png`, animations: "disabled" })
      await page.getByTestId("model-code-close").click()
    } finally {
      await deleteConnector(page, name)
    }
  })
}
