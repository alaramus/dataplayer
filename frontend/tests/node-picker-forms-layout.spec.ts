import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { dismissToast } from "./utils/notices"
import { deleteConnector, openConnector } from "./utils/workspace"

// A select's label is drawn in the label column and also kept, hidden, as
// QSelect's own label, which is where its accessible name comes from; the
// labels below are the visible ones.

/** Where a field's control starts, rather than its label. */
async function controlX(field: Locator) {
  return field.evaluate((el) => {
    const control = el.closest(".q-field")?.querySelector(".q-field__control")
    if (!control) throw new Error("Missing field control")
    return control.getBoundingClientRect().x
  })
}

async function choose(page: Page, testId: string, option: string) {
  await expect(page.getByRole("listbox")).toHaveCount(0)
  await page.getByTestId(testId).click()
  await page.getByRole("option", { name: option, exact: true }).click()
  await expect(page.getByRole("listbox")).toHaveCount(0)
}

// Two connections to the same database: rows are previewed from one into the
// other and never brought in, and no reference is declared.
for (const theme of ["light", "dark"] as const) {
  test(`picking another source keeps the window still in ${theme}`, async ({ page }) => {
    const target = `e2e-picker-target-${theme}-${Date.now()}`
    const source = `e2e-picker-source-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, target)
    await dismissToast(page, "Connection saved")
    await createPostgresConnector(page, source)
    await dismissToast(page, "Connection saved")
    try {
      await openConnector(page, target)
      await pickSchema(page, "demo_lab")
      await openNode(page, "tags")

      await page.getByTestId("grid-import").click()
      const content = page.getByTestId("grid-import-dialog")
      const frame = page.getByRole("dialog").filter({ has: content })
      await expect(content).toBeVisible()
      const before = await frame.boundingBox()
      const sourceField = page.getByTestId("grid-import-source")
      const label = await frame.getByText("Source", { exact: true }).filter({ visible: true }).boundingBox()
      if (!label) throw new Error("Missing source label")
      expect(label.x + label.width).toBeLessThanOrEqual(await controlX(sourceField))

      // The walk stands under the field it answers to, in the control column.
      await choose(page, "grid-import-source", source)
      const schema = page.getByTestId("grid-import-node-demo_lab")
      await expect(schema).toBeVisible()
      expect(Math.abs(((await schema.boundingBox())?.x ?? 0) - await controlX(sourceField))).toBeLessThan(2)
      expect(await frame.boundingBox()).toEqual(before)
      await frame.screenshot({ path: `test-results/import-form-${theme}-walk.png` })
      await schema.click()
      await expect(page.getByTestId("grid-import-back")).toBeVisible()
      await page.getByTestId("grid-import-node-organizations").click()

      // The pairs sit on the window's surface, not in a card of their own.
      const columns = page.getByTestId("grid-import-columns")
      await expect(columns).toBeVisible()
      expect(await columns.evaluate((el) => getComputedStyle(el).borderTopWidth)).toBe("0px")
      await choose(page, "grid-import-pair-label", "display_name")
      await expect(page.getByTestId("grid-import-tally")).toContainText("2 of")
      await page.getByTestId("grid-import-preview").click()
      await expect(content).toContainText("Northstar Labs")
      // Every step so far arrived after the window opened; none moved it (D132).
      expect(await frame.boundingBox()).toEqual(before)
      await expect(page.getByTestId("grid-import-run")).toBeInViewport()
      await frame.screenshot({ path: `test-results/import-form-${theme}.png` })

      // Back lets the chosen table go and shows its schema's tables again; it
      // used to walk up past them and leave the table chosen with no way out.
      await page.getByTestId("grid-import-back").click()
      await expect(page.getByTestId("grid-import-where")).toHaveText("demo_lab")
      await expect(columns).toHaveCount(0)
      await expect(page.getByTestId("grid-import-node-organizations")).toBeVisible()
      expect(await frame.boundingBox()).toEqual(before)
      await page.getByTestId("grid-import-node-organizations").click()
      await expect(page.getByTestId("grid-import-where")).toHaveText("demo_lab / organizations")
      await expect(columns).toBeVisible()

      await page.setViewportSize({ width: 390, height: 600 })
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("grid-import-run")).toBeInViewport()
      await frame.screenshot({ path: `test-results/import-form-${theme}-narrow.png` })
      await frame.getByRole("button", { name: "Cancel", exact: true }).click()
      await expect(content).toHaveCount(0)
      await page.setViewportSize({ width: 1280, height: 720 })

      // Declaring a reference asks the same question in a form of its own.
      await page.getByTestId("grid-structure").click()
      await page.getByTestId("structure-view").getByTestId("structure-declare-reference").click()
      const declare = page.getByTestId("declare-reference-dialog")
      const declareFrame = page.getByRole("dialog").filter({ has: declare })
      await expect(declare).toBeVisible()
      const declareBefore = await declareFrame.boundingBox()
      await choose(page, "declare-reference-near-column", "organization_id")
      await choose(page, "declare-reference-source", source)
      await page.getByTestId("declare-reference-node-demo_lab").click()
      await page.getByTestId("declare-reference-node-organizations").click()
      await expect(page.getByTestId("declare-reference-far-column")).toBeVisible()
      const pointsAt = await declareFrame.getByText("Points at", { exact: true }).filter({ visible: true }).boundingBox()
      const farLabel = await declareFrame.getByText("That column", { exact: true }).filter({ visible: true }).boundingBox()
      if (!pointsAt || !farLabel) throw new Error("Missing declare labels")
      expect(pointsAt.x).toBeCloseTo(farLabel.x, 0)
      expect(await declareFrame.boundingBox()).toEqual(declareBefore)
      await declareFrame.screenshot({ path: `test-results/declare-form-${theme}.png` })
      await declareFrame.getByRole("button", { name: "Cancel", exact: true }).click()
      await expect(declare).toHaveCount(0)
    } finally {
      await page.setViewportSize({ width: 1280, height: 720 })
      await deleteConnector(page, target)
      await deleteConnector(page, source)
    }
  })
}
