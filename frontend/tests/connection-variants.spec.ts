import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { DATABASE, pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, editConnector } from "./utils/workspace"

/**
 * The last part of the connection window: what changes inside it.
 *
 * Neither half can be shown by a unit test. That switching the way of
 * connecting takes the password off the screen and leaves the address alone
 * is a question about what is rendered; that a pasted string fills the fields
 * is a question about the clipboard, the server and the form together.
 */

/** Quasar's select: click the field, then the item by its wording. */
async function chooseAuthMethod(page: Page, label: string) {
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: label, exact: true }).click()
  await expect(page.getByTestId("field-auth_method")).toHaveValue(label)
}

test("switching the way of connecting changes the fields, not the address", async ({
  page,
}) => {
  await login(page)
  await pickAdapterType(page, "postgres")

  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await expect(page.getByTestId("field-password")).toBeVisible()

  await chooseAuthMethod(page, "No auth")

  // The variant's own field is gone — a server configured with `trust` is not
  // sent an empty password, so there is nothing to ask for.
  await expect(page.getByTestId("field-password")).toHaveCount(0)
  // The common fields stayed where they were, with what was typed into them.
  await expect(page.getByTestId("field-host")).toHaveValue(DATABASE.host)
  await expect(page.getByTestId("field-database")).toHaveValue(DATABASE.database)

  await chooseAuthMethod(page, "User & Password")
  await expect(page.getByTestId("field-password")).toBeVisible()
  await expect(page.getByTestId("field-host")).toHaveValue(DATABASE.host)
})

test("a connection saved without a password keeps that way of connecting", async ({
  page,
}) => {
  const name = `e2e-noauth-${Date.now()}`
  await login(page)
  await pickAdapterType(page, "postgres")

  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await chooseAuthMethod(page, "No auth")
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  // Reopened, it comes back on the variant it was stored with rather than on
  // the first one: the discriminator is part of the stored options.
  await editConnector(page, name)
  await expect(page.getByTestId("field-auth_method")).toHaveValue("No auth")
  await expect(page.getByTestId("field-password")).toHaveCount(0)
  await page.getByRole("button", { name: "Cancel" }).click()

  await deleteConnector(page, name)
})

test("a pasted connection string fills the fields and names the method", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await page.evaluate(
    (url) => navigator.clipboard.writeText(url),
    `postgresql://ann:hunter2@${DATABASE.host}:6543/warehouse`
  )

  await pickAdapterType(page, "postgres")
  await page.getByTestId("paste-url").click()

  await expect(page.getByTestId("field-host")).toHaveValue(DATABASE.host)
  await expect(page.getByTestId("field-port")).toHaveValue("6543")
  await expect(page.getByTestId("field-database")).toHaveValue("warehouse")
  await expect(page.getByTestId("field-user")).toHaveValue("ann")
  await expect(page.getByTestId("field-password")).toHaveValue("hunter2")
  // Inferred by the driver from the string carrying a password, never by the
  // form from the presence of a substring.
  await expect(page.getByTestId("field-auth_method")).toHaveValue("User & Password")
})

test("a string with no password comes back as the other way of connecting", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await page.evaluate(
    (url) => navigator.clipboard.writeText(url),
    `postgresql://ann@${DATABASE.host}/warehouse`
  )

  await pickAdapterType(page, "postgres")
  await page.getByTestId("paste-url").click()

  await expect(page.getByTestId("field-auth_method")).toHaveValue("No auth")
  await expect(page.getByTestId("field-password")).toHaveCount(0)
  await expect(page.getByTestId("field-user")).toHaveValue("ann")
})

test("something that is not a connection string is refused, and nothing changes", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await login(page)
  await page.evaluate(() => navigator.clipboard.writeText("just some text"))

  await pickAdapterType(page, "postgres")
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("paste-url").click()

  await expect(page.getByTestId("field-host")).toHaveValue(DATABASE.host)
})
