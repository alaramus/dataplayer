import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { catalogAction, showOnlySchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"
import { deleteConnector, openConnector } from "./utils/workspace"

async function choose(page: Page, field: string, option: string) {
  await page.getByTestId(field).locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' q-field ')][1]").click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test("probe designer geometry", async ({ page }) => {
  const connector = `e2e-probe-${Date.now()}`
  const table = `probe_${Date.now()}`
  await login(page)
  await chooseTheme(page, "dark")
  await createPostgresConnector(page, connector)
  await openConnector(page, connector)
  await showOnlySchema(page, "demo_lab")

  await catalogAction(page, "create_table")
  const designer = page.getByTestId("table-designer")
  const frame = page.getByRole("dialog").filter({ has: designer })
  await expect(designer).toContainText("demo_lab")
  await expect(page.getByTestId("table-schema")).toContainText("demo_lab")
  await expect(page.getByTestId("table-name")).toHaveValue("new table")
  await expect(page.getByTestId("design-identity")).toContainText("Schema")

  await page.getByTestId("table-schema").locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' q-field ')][1]").click()
  await expect(page.getByRole("option", { name: "public", exact: true })).toBeVisible()
  await expect(page.getByRole("option", { name: "pg_catalog", exact: true })).toHaveCount(0)
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("design-sql")).toContainText("SQL preview")
  await expect(page.getByTestId("design-sql")).toContainText("CREATE TABLE")
  await expect(page.getByTestId("design-review-sql")).toBeEnabled()
  const navigation = await page.getByTestId("design-navigation").boundingBox()
  const inspector = await page.getByTestId("design-inspector").boundingBox()
  const preview = await page.getByTestId("design-sql").boundingBox()
  expect(navigation).not.toBeNull()
  expect(inspector).not.toBeNull()
  expect(preview).not.toBeNull()
  expect(navigation!.width).toBeCloseTo(175, 0)
  expect(navigation!.x + navigation!.width).toBeCloseTo(inspector!.x, 0)
  expect(inspector!.x + inspector!.width).toBeCloseTo(preview!.x, 0)
  await expect(frame.getByText("Create table", { exact: true })).toHaveCount(1)
  await page.setViewportSize({ width: 600, height: 700 })
  await expect(page.getByTestId("design-review-sql")).toBeInViewport()
  await expect.poll(() => designer.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await expect.poll(() => frame.locator(".window-dialog__content").evaluate(
    (element) => element.scrollHeight <= element.clientHeight
  )).toBe(true)
  await page.setViewportSize({ width: 1280, height: 720 })
  const stableFrame = await frame.boundingBox()
  console.log("FRAME " + JSON.stringify(stableFrame))
  await expect.poll(() => designer.locator(".q-field").evaluateAll(
    (fields) => fields.length > 0 && fields.every((field) => field.classList.contains("q-field--outlined"))
  )).toBe(true)
  await expect(page.getByTestId("column-not-null").locator(".q-checkbox__inner"))
    .toHaveClass(/text-dp-control-selected/)

  await page.getByTestId("table-name").fill(table)
  await page.getByTestId("column-name").fill("id")
  await choose(page, "column-type", "Integer")
  await choose(page, "column-generation", "Identity")
  await page.getByTestId("add-columns").click()
  await page.getByTestId("column-name").fill("label")
  await choose(page, "column-type", "Text")

  const probe = await page.evaluate(() => {
    const box = (selector: string) => {
      const element = document.querySelector(selector)
      if (!element) return null
      const rect = element.getBoundingClientRect()
      return { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
    }
    const checkbox = document.querySelector('[data-testid="column-not-null"]')!
    const rect = checkbox.getBoundingClientRect()
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
    const editor = document.querySelector('[data-testid="design-inspector"]')!
    const body = document.querySelector('[data-testid="design-body"]')!
    return {
      checkbox: box('[data-testid="column-not-null"]'),
      editorScroll: { top: editor.scrollTop, left: editor.scrollLeft, sh: editor.scrollHeight, ch: editor.clientHeight },
      bodyScroll: { top: body.scrollTop, sh: body.scrollHeight, ch: body.clientHeight },
      editor: box('[data-testid="design-inspector"]'),
      sql: box('[data-testid="design-sql"]'),
      body: box('[data-testid="design-body"]'),
      hit: hit ? `${hit.tagName}.${String(hit.className).slice(0, 80)}` : "none",
    }
  })
  console.log("PROBE " + JSON.stringify(probe))

  await page.getByTestId("column-not-null").click()
  await deleteConnector(page, connector)
})
