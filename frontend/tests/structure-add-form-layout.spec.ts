import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { openNode, pickSchema } from "./utils/catalog"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

for (const theme of ["light", "dark"] as const) {
  test(`structure addition forms reflow and keep their geometry in ${theme}`, async ({ page }) => {
    const name = `e2e-add-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await page.getByTestId("toast").filter({ hasText: "Connection saved" })
      .getByRole("button", { name: "Dismiss", exact: true }).click()
    await openConnector(page, name)
    await pickSchema(page, "demo_lab")
    await openNode(page, "app_users")
    await page.getByTestId("grid-structure").click()
    await page.route(/\/api\/v1\/connectors\/[^/]+\/(columns|indexes|constraints)$/, (route) =>
      route.fulfill({ status: 400, json: { detail: "The source refused this change. ".repeat(16) } }))
    const choose = async (id: string, option: string) => {
      await page.getByTestId(id).click()
      await page.getByRole("option", { name: option, exact: true }).click()
    }
    try {
      for (const kind of ["add", "index", "constraint"] as const) {
        const command = kind === "add" ? "column" : kind
        await page.getByTestId(`structure-add-${command}`).click()
        const content = page.getByTestId(`structure-${kind}-dialog`)
        const frame = page.getByRole("dialog").filter({ has: content })
        await expect(content).toBeVisible()
        const before = await frame.boundingBox()
        if (kind === "add") {
          await page.getByTestId("structure-add-name").fill("layout_example")
          const fieldX = await page.getByTestId("structure-add-name").evaluate((el) => {
            const control = el.closest(".q-field")?.querySelector(".q-field__control")
            if (!control) throw new Error("Missing field control")
            return control.getBoundingClientRect().x
          })
          const checkbox = await page.getByTestId("structure-add-nullable").boundingBox()
          if (!checkbox) throw new Error("Missing checkbox")
          expect(checkbox.x).toBeCloseTo(fieldX, 0)
          await page.getByTestId("structure-add-nullable").press("Space")
          await expect(page.getByTestId("structure-add-nullable")).toHaveAttribute("aria-checked", "false")
        } else {
          await choose(`structure-${kind}-columns`, "organization_id")
          await page.keyboard.press("Escape")
          if (kind === "index") {
            await choose("structure-index-columns", "email")
            await page.keyboard.press("Escape")
            await choose("structure-index-method", "Hash")
            await expect(page.getByTestId("structure-index-save")).toBeDisabled()
            await expect(page.getByTestId("structure-index-unique")).toHaveAttribute("aria-disabled", "true")
            expect(await frame.boundingBox()).toEqual(before)
            await choose("structure-index-method", "B-tree")
            await page.getByTestId("structure-index-unique").press("Space")
            await expect(page.getByTestId("structure-index-unique")).toHaveAttribute("aria-checked", "true")
            const color = await page.getByTestId("structure-index-unique").evaluate((el) => {
              const mark = el.querySelector(".q-checkbox__inner")
              if (!mark) throw new Error("Missing checkbox mark")
              return getComputedStyle(mark).color
            })
            const channels = (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number)
            expect(channels).toHaveLength(3)
            expect(Math.max(...channels) - Math.min(...channels)).toBe(0)
          } else {
            await choose("structure-constraint-kind", "Foreign key")
            await choose("structure-constraint-target", "organizations")
            await expect(page.getByTestId("structure-constraint-key")).toBeVisible()
            expect(await frame.boundingBox()).toEqual(before)
          }
        }
        await expect(page.getByRole("listbox")).toHaveCount(0)
        await frame.screenshot({ path: `test-results/structure-${kind}-${theme}.png` })
        await page.getByTestId(`structure-${kind}-save`).click()
        await expect(page.getByTestId(`structure-${kind}-error`)).toContainText("The source refused")
        expect(await frame.boundingBox()).toEqual(before)
        await page.setViewportSize({ width: 390, height: 600 })
        await expect(page.getByTestId(`structure-${kind}-save`)).toBeInViewport()
        await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
        const body = content.locator(".window-dialog__content")
        expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
        await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
        await frame.screenshot({ path: `test-results/structure-${kind}-${theme}-narrow-error.png` })
        await frame.getByRole("button", { name: "Cancel", exact: true }).click()
        await page.setViewportSize({ width: 1280, height: 900 })
      }
    } finally {
      await deleteConnector(page, name)
    }
  })
}
