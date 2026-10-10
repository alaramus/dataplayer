import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"
import { closeWindowDialog, connectorRow, deleteConnector } from "./utils/workspace"

/**
 * The catalog is the screen a new user meets first, and most of what it says
 * cannot be proved by a unit test: the short lists are read on the server from
 * the type's page of the guide (D183), travel through the generated client and
 * end up in the panel. A caption can be computed and unit-tested and still
 * never be rendered.
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
  // Plain items a person reads, not the driver's list of functions.
  await expect(panel.getByTestId("adapter-can-see").getByRole("listitem").first())
    .toHaveText("Folders and files, and what each one is: its size, its dates, its format")
  await expect(panel.getByTestId("adapter-can-change")).toContainText("Files in a text editor")
  await expect(panel).not.toContainText("Browse the catalog")

  // Editing a table is one item, not Add columns, Drop columns and Edit rows.
  await page.getByTestId("adapter-postgres").click()
  await expect(panel.getByTestId("adapter-can-change")).toContainText("Table data and columns")
  await expect(panel).not.toContainText("Drop columns")
  await expect(panel).not.toContainText("Files in a text editor")
})

test("finds a type by what it can do, not only by its name", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()

  await page.getByTestId("adapter-search").fill("upload")

  // Nothing in the name "Files" says upload; the word is in its short list.
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

/** What a colour token comes to on this page, for comparing with a drawn one. */
async function tokenColour(page: Page, token: string): Promise<string> {
  return await page.evaluate((name) => {
    const probe = document.createElement("span")
    probe.style.background = `var(${name})`
    document.body.append(probe)
    const colour = getComputedStyle(probe).backgroundColor
    probe.remove()
    return colour
  }, token)
}

// The category shown is the current page of the list, on the tab ground as
// every list's current entry is (D186); the tile picked is a choice, washed
// and outlined.
test("marks the chosen type and category in grey, as every other list does", async ({ page }) => {
  await login(page)

  for (const theme of ["light", "dark"] as const) {
    await chooseTheme(page, theme)
    await page.getByTestId("add-connector").click()
    await page.getByTestId("adapter-category-sql").click()
    await page.getByTestId("adapter-postgres").click()

    const grey = await tokenColour(page, "--dp-active")
    const tile = page.getByTestId("adapter-postgres")
    await expect(tile).toHaveCSS("background-color", grey)
    await expect(tile).toHaveCSS("border-top-color", await tokenColour(page, "--dp-focus-border"))
    await expect(tile).toHaveCSS("box-shadow", "none")
    await expect(page.getByTestId("adapter-category-sql")).toHaveCSS(
      "background-color", await tokenColour(page, "--dp-tab-current")
    )
    await page.getByTestId("adapter-catalog").screenshot({ path: `test-results/adapter-catalog-${theme}.png` })
    await closeWindowDialog(page, "adapter-catalog")
  }
  await chooseTheme(page, "light")
})

test("opens the guide of a type, walks its links, and stays open beside the form", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-postgres").click()
  await page.getByTestId("adapter-guide").click()

  const guide = page.getByTestId("guide-window")
  const text = guide.getByTestId("guide-text")
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("PostgreSQL")
  // The same words as the panel: one text in two places.
  await expect(text).toContainText("Table data and columns")
  await expect(text.getByRole("heading", { name: "Connecting" })).toBeVisible()
  await expect(guide.getByTestId("guide-back")).toBeDisabled()
  await page.screenshot({ path: "test-results/adapter-guide.png" })

  // A link to another page turns the window to it, and Back returns.
  await text.getByText("Connections", { exact: true }).first().click()
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("Connections")
  await guide.getByTestId("guide-back").click()
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("PostgreSQL")

  // Another type's Guide turns the open window rather than opening a second.
  // The guide opened over the catalog, so the catalog is brought forward
  // first, by the part of it still showing, as a person would.
  const catalogBox = await page.getByTestId("adapter-catalog").boundingBox()
  const guideBox = await page.getByTestId("window-guide").boundingBox()
  if (catalogBox === null || guideBox === null) throw new Error("a window has no box")
  await page.mouse.click(guideBox.x + guideBox.width + 16, catalogBox.y + 24)
  await page.getByTestId("adapter-redis").click()
  await page.getByTestId("adapter-guide").click()
  await expect(page.getByTestId("guide-window")).toHaveCount(1)
  await expect(text.getByRole("heading", { level: 1 })).toHaveText("Redis")

  // Read while the connection is filled in: the catalog goes, the guide stays.
  await page.getByTestId("create-from-catalog").click()
  await expect(page.getByTestId("adapter-catalog")).toHaveCount(0)
  await expect(page.getByTestId("connector-name")).toBeVisible()
  await expect(guide).toBeVisible()
})

test("says what a start runs on hover, and leaves the panel to its short lists", async ({ page }) => {
  await login(page)
  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-postgres").click()
  const panel = page.getByTestId("adapter-panel")
  await expect(panel.getByTestId("adapter-can-change")).toBeVisible()

  // What it runs, or why it cannot, is not written under the button.
  const offer = panel.getByTestId("start-service-offer-postgres")
  await expect(offer).toBeVisible()
  await expect(panel).not.toContainText("saves the connection")
  await offer.hover()
  // Whether this server can start it or not, the tooltip says something:
  // it once received its words as an attribute and showed an empty box.
  await expect(page.getByRole("tooltip")).toHaveText(/Runs postgres|\S/)
  await expect(page.getByRole("tooltip")).not.toBeEmpty()

  await page.getByTestId("adapter-catalog").screenshot({ path: "test-results/adapter-catalog-tooltips.png" })
})
