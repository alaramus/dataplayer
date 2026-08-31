import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { connectorRow, deleteConnector } from "./utils/workspace"

/**
 * The catalog is the screen a new user meets first, and most of what it says
 * cannot be proved by a unit test: the capabilities are computed on the
 * server, travel through the generated client and end up as chips. Captions
 * in the old catalog tree were computed, unit-tested and never rendered.
 */

test("shows what a source type can do before anything is filled in", async ({ page }) => {
  await login(page)

  await page.getByTestId("add-connector").click()
  const catalog = page.getByTestId("adapter-catalog")
  await expect(catalog).toBeVisible()

  // Both types, each under its own category, counted.
  await expect(page.getByTestId("adapter-postgres")).toBeVisible()
  await expect(page.getByTestId("adapter-file")).toBeVisible()
  await expect(page.getByTestId("adapter-category-sql")).toContainText("SQL Databases")

  // Nothing is claimed until a type is picked.
  await expect(catalog).toContainText("Pick a source type")

  await page.getByTestId("adapter-file").click()
  const panel = page.getByTestId("adapter-panel")
  await expect(panel).toContainText("Your personal storage")
  await expect(panel).toContainText("Browse the catalog")
  // Derived from the action classes the driver dispatches, so this chip and
  // the menu in the catalog cannot disagree about what a file source offers.
  await expect(panel).toContainText("Upload files")
  await expect(panel).toContainText("Delete")

  // PostgreSQL implements no actions, and must therefore claim none: the
  // whole point of deriving the list rather than writing it down.
  await page.getByTestId("adapter-postgres").click()
  await expect(panel).toContainText("Read rows")
  await expect(panel).not.toContainText("Upload files")
})

test("finds a type by what it can do, not only by its name", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()

  await page.getByTestId("adapter-search").fill("upload")

  // Nothing in "Files" says upload; the word comes from the capability.
  await expect(page.getByTestId("adapter-file")).toBeVisible()
  await expect(page.getByTestId("adapter-postgres")).toHaveCount(0)

  await page.getByTestId("adapter-search").fill("nothing-is-called-this")
  await expect(page.getByTestId("adapter-catalog")).toContainText("No source type matches")
})

test("a category filters the grid, and All brings it back", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()

  await page.getByTestId("adapter-category-sql").click()
  await expect(page.getByTestId("adapter-postgres")).toBeVisible()
  await expect(page.getByTestId("adapter-file")).toHaveCount(0)

  await page.getByTestId("adapter-category-all").click()
  await expect(page.getByTestId("adapter-file")).toBeVisible()
})

test("the catalog leads to the form, and back again", async ({ page }) => {
  const name = `e2e-catalog-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-file").click()
  await page.getByTestId("create-from-catalog").click()

  // The form follows the type picked in the window behind it, and says so by
  // the name it opens with — there is one driver per type, so a row stating
  // which one would only ever repeat this.
  await expect(page.getByTestId("connector-name")).toHaveValue("Files")
  await expect(page.getByTestId("adapter-catalog")).toHaveCount(0)

  await page.getByTestId("back-to-catalog").click()
  await expect(page.getByTestId("adapter-catalog")).toBeVisible()

  // A different type this time, and the form follows it rather than the one
  // picked before.
  await page.getByTestId("adapter-postgres").click()
  await page.getByTestId("create-from-catalog").click()
  await expect(page.getByTestId("connector-name")).toHaveValue("PostgreSQL")
  await expect(page.getByTestId("field-host")).toBeVisible()

  await page.getByTestId("back-to-catalog").click()
  await page.getByTestId("adapter-file").click()
  await page.getByTestId("create-from-catalog").click()
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("editing an existing connection opens its form directly", async ({ page }) => {
  const name = `e2e-edit-direct-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-file").click()
  await page.getByTestId("create-from-catalog").click()
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await page.getByTestId(`connector-edit-${name}`).click()

  // No catalog, and nothing to go back to: the type of a stored connection is
  // settled, so there was never a step before this one.
  await expect(page.getByTestId("adapter-catalog")).toHaveCount(0)
  await expect(page.getByTestId("back-to-catalog")).toHaveCount(0)
  await expect(page.getByTestId("connector-name")).toHaveValue(name)

  await page.getByRole("button", { name: "Cancel" }).click()
  await deleteConnector(page, name)
})
