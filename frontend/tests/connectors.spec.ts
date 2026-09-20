import { expect, test } from "@playwright/test"
import type { Locator } from "@playwright/test"

import { chooseTabColor, DATABASE, openPermissions, pickAdapterType } from "./utils/connectors"
import { openNode } from "./utils/catalog"
import { login } from "./utils/login"
import { catalogTab, connectorRow, deleteConnector, editConnector, openConnector, rowsTabs } from "./utils/workspace"


// Quasar forwards data-testid onto the input element, so field ids address the
// input directly, without a nested locator.
//
// The type is no longer among them: it is chosen in the catalog before this
// window opens, and the form only states which one it was.
async function fillConnectionFields(
  page: import("@playwright/test").Page,
  password: string
) {
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(password)
}

test("a connector color follows its open tabs and can be reset after reload", async ({ page }) => {
  const name = `e2e-colored-${Date.now()}`
  await login(page)
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)
  await chooseTabColor(page, "#246abc")
  await page.getByTestId("save-connector").click()
  await openConnector(page, name)
  await openNode(page, "connector")
  await openNode(page, "user")
  await expect(rowsTabs(page)).toHaveCount(2)
  const tabs = [catalogTab(page), rowsTabs(page).nth(0), rowsTabs(page).nth(1)]
  for (const tab of tabs) {
    await expect(tab).toHaveCSS("background-color", "rgb(36, 106, 188)")
    await expect(tab).toHaveCSS("color", "rgb(255, 255, 255)")
  }

  // The tab being read and the one beside it are the same size and the same
  // weight: only the line under the active one says which is which, so
  // pressing a tab does not move the tabs around it.
  const shape = (tab: Locator) =>
    tab.evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        weight: style.fontWeight,
        height: Math.round(element.getBoundingClientRect().height),
        padding: `${style.paddingTop} ${style.paddingRight}`,
      }
    })
  const activeRows = await shape(rowsTabs(page).nth(1))
  expect(await shape(rowsTabs(page).nth(0))).toEqual(activeRows)

  // And the row this was opened from is marked in the same colour, so the row
  // and the tabs it opened are visibly one thing.
  await expect(connectorRow(page, name)).toHaveCSS("background-color", "rgb(36, 106, 188)")
  await expect(connectorRow(page, name)).toHaveCSS("color", "rgb(255, 255, 255)")
  // And the pointer arriving at the row does not take the colour off it.
  await connectorRow(page, name).hover()
  await expect(connectorRow(page, name)).toHaveCSS("background-color", "rgb(36, 106, 188)")

  // The catalog carries it too, for the mark that points at a row: that mark
  // is the answer to a press on the tab of a table, and the tab is drawn in
  // this colour.
  await expect(page.getByTestId("catalog-list")).toHaveCSS("--dp-panel-background", "#246abc")

  await editConnector(page, name)
  await chooseTabColor(page, "#ffffff")
  // Draft choices do not recolor the workspace until Apply or OK.
  for (const tab of tabs) await expect(tab).toHaveCSS("background-color", "rgb(36, 106, 188)")
  await page.getByTestId("apply-connector").click()
  for (const tab of tabs) {
    await expect(tab).toHaveCSS("background-color", "rgb(255, 255, 255)")
    await expect(tab).toHaveCSS("color", "rgb(0, 0, 0)")
  }
  await page.getByTestId("cancel-connector").click()
  await page.reload()
  for (const tab of tabs) await expect(tab).toHaveCSS("background-color", "rgb(255, 255, 255)")

  await editConnector(page, name)
  await page.getByTestId("connector-tab-color").click()
  const picker = page.getByRole("dialog", { name: "Tab color", exact: true })
  await expect(picker.getByRole("textbox")).toHaveValue(/#ffffff/i)
  await picker.getByRole("button", { name: "Reset color", exact: true }).click()
  await page.getByTestId("apply-connector").click()
  for (const tab of tabs) await expect(tab).toHaveCSS("--dp-panel-background", "")
  // A connection with no colour of its own is drawn like one that has it:
  // filled, and the same shape. The colour is the only difference the choice
  // makes.
  for (const tab of tabs) await expect(tab).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)")
  expect(await shape(rowsTabs(page).nth(1))).toEqual(activeRows)
  expect(await shape(rowsTabs(page).nth(0))).toEqual(activeRows)
  await page.getByTestId("cancel-connector").click()
  await page.reload()
  for (const tab of tabs) await expect(tab).toHaveCSS("--dp-panel-background", "")
  await expect(page.getByTestId("catalog-list")).toHaveCSS("--dp-panel-background", "")
  // A connection with no colour of its own is marked in the plain one, and
  // the plain one is what its tabs are filled with: the mark is the same mark
  // either way, and only the colour of it was ever a choice. Asked of the tab
  // rather than written down, so this holds in either theme.
  await page.mouse.move(0, 0)
  const plain = await catalogTab(page).evaluate(
    (element) => getComputedStyle(element).backgroundColor
  )
  expect(plain).not.toBe("rgba(0, 0, 0, 0)")
  await expect(connectorRow(page, name)).toHaveCSS("background-color", plain)
  await deleteConnector(page, name)
})

test("creates a connection, checks it and deletes it", async ({ page }) => {
  const name = `e2e-postgres-${Date.now()}`
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)

  await page.getByTestId("check-draft").click()
  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toContainText("Succeeded")

  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  // Checking a stored connection is the same window and the same button: one
  // home for the command, so the two cannot drift apart.
  await editConnector(page, name)
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toContainText("Succeeded")
  await page.getByRole("button", { name: "Cancel" }).click()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the window separates how to reach a connection from what may be done through it", async ({
  page,
}) => {
  const name = `e2e-pages-${Date.now()}`
  await login(page)

  // Both pages from the start. Whoever registers a source is the person who
  // knows whether anybody should be able to write through it, and the address
  // is what opens (D66).
  await pickAdapterType(page, "postgres")
  await expect(page.getByTestId("connector-tabs")).toBeVisible()
  await expect(page.getByTestId("field-host")).toBeVisible()
  await expect(page.getByTestId("connector-url")).toBeVisible()

  await openPermissions(page)
  await expect(page.getByTestId("connector-policy")).toBeVisible()
  await expect(page.getByTestId("field-host")).toBeHidden()
  // The connection string is composed from the fields, so it belongs to them.
  await expect(page.getByTestId("connector-url")).toBeHidden()
  // The name and whether the connection is in use belong to neither page:
  // they name the thing both pages are about.
  await expect(page.getByTestId("connector-name")).toBeVisible()
  // Nothing to give away yet, so there is nobody to give it to.
  await expect(page.getByTestId("share-connector")).toHaveCount(0)

  // Nothing read through a new connection leaves the server until its owner
  // says so (D135).
  const transfer = page.getByTestId("connector-third-party")
  await expect(transfer).not.toBeChecked()
  await expect(transfer).toBeEnabled()

  await page.getByTestId("connector-policy").click()
  await page.getByRole("option", { name: "Read only", exact: true }).click()
  await transfer.click()
  await expect(transfer).toBeChecked()
  await page.getByTestId("connector-tab-general").click()
  await expect(page.getByTestId("field-host")).toBeVisible()
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  // What was chosen while creating it is what it was created with, rather
  // than a default somebody has to go back and correct.
  await editConnector(page, name)
  await openPermissions(page)
  await expect(page.getByTestId("connector-policy")).toContainText("Read only")
  await expect(page.getByTestId("connector-third-party")).toBeChecked()
  await expect(page.getByTestId("share-connector")).toBeVisible()

  await page.getByRole("button", { name: "Cancel" }).click()
  await deleteConnector(page, name)
})

test("a wrong password reports an auth failure without leaking the password", async ({
  page,
}) => {
  const wrongPassword = "definitely-not-the-password"
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(`e2e-bad-${Date.now()}`)
  await fillConnectionFields(page, wrongPassword)

  await page.getByTestId("check-draft").click()

  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toContainText("Failed")
  await expect(result).toContainText("Authentication failed")
  await expect(result).not.toContainText(wrongPassword)
})

test("a stored secret stands in for itself and needs no retyping", async ({
  page,
}) => {
  const name = `e2e-edit-${Date.now()}`
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await editConnector(page, name)
  // Not empty: an empty box beside a saved connection reads as a password
  // that was lost. It says there is one and that it is not being shown.
  await expect(page.getByTestId("field-password")).toHaveValue("<hidden>")

  // Entering the field means meaning to replace it, so the stand-in gives way
  // to an empty one.
  await page.getByTestId("field-password").click()
  await expect(page.getByTestId("field-password")).toHaveValue("")

  // Leaving it without typing changed nothing, so the stand-in comes back: an
  // empty box would go on claiming there is no password stored.
  await page.getByTestId("field-user").click()
  await expect(page.getByTestId("field-password")).toHaveValue("<hidden>")

  // What is typed stays, because that is what replaces the stored value.
  await page.getByTestId("field-password").fill("something-else")
  await page.getByTestId("field-user").click()
  await expect(page.getByTestId("field-password")).toHaveValue("something-else")
  await page.getByTestId("field-password").fill("")
  await page.getByTestId("field-user").click()
  await expect(page.getByTestId("field-password")).toHaveValue("<hidden>")

  // Left blank, nothing is sent and the server substitutes the stored value
  // by connector_id.
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toContainText("Succeeded")

  await page.getByRole("button", { name: "Cancel" }).click()
  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the result of a check sits between the form and footer", async ({ page }) => {
  await login(page)
  await pickAdapterType(page, "postgres")
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("check-draft").click()

  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()

  const panel = await result.boundingBox()
  const button = await page.getByTestId("check-draft").boundingBox()
  const url = await page.getByTestId("connector-url").boundingBox()
  if (!panel || !button || !url) throw new Error("nothing was laid out")

  // Above the button, and near enough to belong to it.
  expect(panel.y + panel.height).toBeLessThanOrEqual(button.y)
  expect(button.y - (panel.y + panel.height)).toBeLessThan(30)
  expect(panel.y).toBeGreaterThanOrEqual(url.y + url.height)

  // And it goes away when it has been read, rather than staying in the way.
  await page.getByTestId("dismiss-check-result").click()
  await expect(result).toHaveCount(0)
})
