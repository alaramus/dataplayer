import { expect, test } from "@playwright/test"

import { DATABASE, pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, editConnector } from "./utils/workspace"


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

test("creates a connection, checks it and deletes it", async ({ page }) => {
  const name = `e2e-postgres-${Date.now()}`
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)

  await page.getByTestId("check-draft").click()
  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/check-popover--ok/)

  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  // Checking a stored connection is the same window and the same button: one
  // home for the command, so the two cannot drift apart.
  await editConnector(page, name)
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toHaveClass(/check-popover--ok/)
  await page.getByRole("button", { name: "Cancel" }).click()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
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
  await expect(result).toHaveClass(/check-popover--failed/)
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
  await expect(page.getByTestId("check-result")).toHaveClass(/check-popover--ok/)

  await page.getByRole("button", { name: "Cancel" }).click()
  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the result of a check appears over the button that ran it", async ({ page }) => {
  // A panel rather than a line in the form: the answer is read once and
  // dismissed, and a line in the body moved every field below it. Whether one
  // rectangle sits above another is a question only a browser can answer.
  await login(page)
  await pickAdapterType(page, "postgres")
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("check-draft").click()

  const popover = page.getByTestId("check-result")
  await expect(popover).toBeVisible()

  const panel = await popover.boundingBox()
  const button = await page.getByTestId("check-draft").boundingBox()
  const url = await page.getByTestId("connector-url").boundingBox()
  if (!panel || !button || !url) throw new Error("nothing was laid out")

  // Above the button, and near enough to belong to it.
  expect(panel.y + panel.height).toBeLessThanOrEqual(button.y)
  expect(button.y - (panel.y + panel.height)).toBeLessThan(30)
  // And over the form rather than inside it: a panel that took space of its
  // own would sit clear of the row it now covers.
  expect(panel.y).toBeLessThan(url.y)
  expect(panel.y + panel.height).toBeGreaterThan(url.y + url.height)

  // And it goes away when it has been read, rather than staying in the way.
  await page.getByTestId("dismiss-check-result").click()
  await expect(popover).toHaveCount(0)
})
