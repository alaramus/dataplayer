import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { catalogAction, openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { dismissToast } from "./utils/notices"
import { deleteConnector, openConnector } from "./utils/workspace"

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

/** A legend heading stands over the fields of its column. */
async function expectHeadingOver(pairs: Locator, heading: string, field: Locator) {
  const box = await pairs.getByText(heading, { exact: true }).boundingBox()
  if (!box) throw new Error(`Missing heading ${heading}`)
  expect(Math.abs(box.x - await controlX(field))).toBeLessThan(2)
}

// Nothing is created: every window ends on Cancel.
for (const theme of ["light", "dark"] as const) {
  test(`creating a table keeps its window and pairs aligned in ${theme}`, async ({ page }) => {
    const name = `e2e-create-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await dismissToast(page, "Connection saved")
    try {
      await openConnector(page, name)
      await pickSchema(page, "demo_lab")

      // From a file: the pairs and a preview arrive once the file is read.
      await catalogAction(page, "load_csv")
      const file = page.getByTestId("file-to-relation-dialog")
      const fileFrame = page.getByRole("dialog").filter({ has: file })
      await expect(file).toBeVisible()
      const fileBefore = await fileFrame.boundingBox()
      await page.getByTestId("load-file").setInputFiles({
        name: "regions.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("code,label\nEU,Europe\nUS,United States\n"),
      })
      const filePairs = page.getByTestId("load-columns")
      await expect(page.getByTestId("load-tally")).toHaveText("all 2")
      await expectHeadingOver(filePairs, "Column in the new table",
        page.getByTestId("load-column-code").getByRole("textbox"))
      await choose(page, "load-schema-mode", "Create new schema")
      await expect(page.getByTestId("load-new-schema")).toBeVisible()
      expect(await fileFrame.boundingBox()).toEqual(fileBefore)
      await fileFrame.screenshot({ path: `test-results/create-from-file-${theme}.png` })
      await page.setViewportSize({ width: 390, height: 600 })
      await expect.poll(() => file.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("load-create")).toBeInViewport()
      await fileFrame.screenshot({ path: `test-results/create-from-file-${theme}-narrow.png` })
      await fileFrame.getByRole("button", { name: "Cancel", exact: true }).click()
      await expect(file).toHaveCount(0)
      await page.setViewportSize({ width: 1280, height: 720 })

      // From rows: the pairs and their types arrive once the destination answers.
      await openNode(page, "tags")
      await page.getByTestId("grid-create-table").click()
      const rows = page.getByTestId("grid-create-table-dialog")
      const rowsFrame = page.getByRole("dialog").filter({ has: rows })
      await expect(rows).toBeVisible()
      const rowsBefore = await rowsFrame.boundingBox()
      await choose(page, "grid-create-table-connector", name)
      const rowPairs = page.getByTestId("grid-create-table-columns")
      await expect(rowPairs).toBeVisible()
      const label = page.getByTestId("grid-create-table-column-label")
      await expectHeadingOver(rowPairs, "Column in the new table", label.getByRole("textbox"))
      await expectHeadingOver(rowPairs, "Type", label.getByRole("combobox"))
      // A row left out keeps its place, its fields go quiet and its arrow goes.
      await page.getByTestId("grid-create-table-column-color").getByRole("switch").click()
      await expect(page.getByTestId("grid-create-table-column-color").getByRole("textbox")).toBeDisabled()
      expect(await rowsFrame.boundingBox()).toEqual(rowsBefore)
      await rowsFrame.screenshot({ path: `test-results/create-from-rows-${theme}.png` })
      await page.setViewportSize({ width: 390, height: 600 })
      await expect.poll(() => rows.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("grid-create-table-run")).toBeInViewport()
      await rowsFrame.screenshot({ path: `test-results/create-from-rows-${theme}-narrow.png` })
      await rowsFrame.getByRole("button", { name: "Cancel", exact: true }).click()
      await expect(rows).toHaveCount(0)
    } finally {
      await page.setViewportSize({ width: 1280, height: 720 })
      await deleteConnector(page, name)
    }
  })
}
