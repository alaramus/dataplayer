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
 * is a question about what is rendered; that an address typed into the URL
 * box fills the fields is a question about the form and the server together.
 */

/** Quasar's select: click the field, then the item by its wording. */
async function chooseAuthMethod(page: Page, label: string) {
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: label, exact: true }).click()
  await expect(page.getByTestId("field-auth_method")).toHaveValue(label)
}

/** Type an address into the URL box and wait for it to reach the fields. */
async function typeUrl(page: Page, url: string) {
  await page.getByTestId("connector-url").fill(url)
  await page.getByTestId("connector-name").click()
}

test("a form that has only its defaults is already addressed", async ({ page }) => {
  // The defaults put a host and a port there before anything is typed, and
  // that is an address worth showing. Composed by the server like every other
  // one: a client that wrote this one itself would be a second copy of the
  // driver's grammar, differing from it in the quoting first.
  await login(page)
  await pickAdapterType(page, "postgres")

  const control = (testId: string) =>
    page.locator(".q-field").filter({ has: page.getByTestId(testId) }).first().locator(".q-field__control")
  const authentication = await control("field-auth_method").boundingBox()
  const host = await control("field-host").boundingBox()
  expect(authentication?.height, "the select and text field should share a control height").toBe(host?.height)

  await expect(page.getByTestId("connector-url")).toHaveValue("postgresql://localhost:5432")

  // And it grows a part at a time, rather than appearing only once every
  // required field is filled in.
  await page.getByTestId("field-user").fill("ann")
  await expect(page.getByTestId("connector-url")).toHaveValue("postgresql://ann@localhost:5432")

  await page.getByTestId("field-database").fill("warehouse")
  await expect(page.getByTestId("connector-url")).toHaveValue(
    "postgresql://ann@localhost:5432/warehouse"
  )
})

test("a source with no address still shows no box while being filled in", async ({
  page,
}) => {
  // Incomplete and "has none at all" are different answers, and only the
  // second one takes the row away.
  await login(page)
  await pickAdapterType(page, "file")

  await expect(page.getByTestId("connector-url")).toHaveCount(0)
})

test("the choice of method stands directly under the address", async ({ page }) => {
  // Order is the server's statement, made by declaring the fields in it. A
  // form that gathered every shared field first would put the choice under
  // the database instead, whatever the model said.
  await login(page)
  await pickAdapterType(page, "postgres")

  const middle = async (id: string) => {
    const box = await page.getByTestId(id).boundingBox()
    if (!box) throw new Error(`${id} was not laid out`)
    return box.y + box.height / 2
  }

  const port = await middle("field-port")
  const auth = await middle("field-auth_method")
  const database = await middle("field-database")

  expect(auth).toBeGreaterThan(port)
  expect(auth).toBeLessThan(database)
})

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

test("an address typed into the URL box fills the fields and names the method", async ({
  page,
}) => {
  await login(page)
  await pickAdapterType(page, "postgres")

  await typeUrl(page, `postgresql://ann:hunter2@${DATABASE.host}:6543/warehouse`)

  await expect(page.getByTestId("field-host")).toHaveValue(DATABASE.host)
  await expect(page.getByTestId("field-port")).toHaveValue("6543")
  await expect(page.getByTestId("field-database")).toHaveValue("warehouse")
  await expect(page.getByTestId("field-user")).toHaveValue("ann")
  await expect(page.getByTestId("field-password")).toHaveValue("hunter2")
  // Inferred by the driver from the string carrying a password, never by the
  // form from the presence of a substring.
  await expect(page.getByTestId("field-auth_method")).toHaveValue("User & Password")
})

test("the box then shows what the fields compose, without the password", async ({
  page,
}) => {
  // Which of the two is true is answered by the box never keeping an answer
  // of its own: the password lands in its field and leaves the box.
  await login(page)
  await pickAdapterType(page, "postgres")

  await typeUrl(page, `postgresql://ann:hunter2@${DATABASE.host}:6543/warehouse`)

  await expect(page.getByTestId("connector-url")).toHaveValue(
    `postgresql://ann@${DATABASE.host}:6543/warehouse`
  )
})

test("a string with no password comes back as the other way of connecting", async ({
  page,
}) => {
  await login(page)
  await pickAdapterType(page, "postgres")

  await typeUrl(page, `postgresql://ann@${DATABASE.host}/warehouse`)

  await expect(page.getByTestId("field-auth_method")).toHaveValue("No auth")
  await expect(page.getByTestId("field-password")).toHaveCount(0)
  await expect(page.getByTestId("field-user")).toHaveValue("ann")
})

test("what is being typed is never rewritten under the cursor", async ({ page }) => {
  // Every prefix of an address parses as some address, and the fields follow
  // each one. If the box also followed the fields it would be rewritten
  // between keystrokes, and the address could not be typed out at all.
  await login(page)
  await pickAdapterType(page, "postgres")

  // The box is not empty to begin with: the defaults give a host and a port,
  // and the server composes an address from them before anything is typed.
  // Selected rather than cleared through the field, so that what follows is
  // keystrokes and nothing else — which is the whole subject of this test.
  await page.getByTestId("connector-url").click()
  await expect(page.getByTestId("connector-url")).toHaveValue("postgresql://localhost:5432")
  await page.keyboard.press("ControlOrMeta+a")
  await page.keyboard.type(`postgresql://ann@${DATABASE.host}/warehouse`)
  // Long enough for the prefix to be parsed and for the fields to compose an
  // address of their own — which is the moment a slow typist would have the
  // box rewritten from under them, port and all.
  await page.waitForTimeout(1500)
  await page.keyboard.type("2")

  await expect(page.getByTestId("connector-url")).toHaveValue(
    `postgresql://ann@${DATABASE.host}/warehouse2`
  )

  // Leaving hands the box back to the fields, and the password is not part of
  // what they compose.
  await page.getByTestId("connector-name").click()
  await expect(page.getByTestId("connector-url")).toHaveValue(
    `postgresql://ann@${DATABASE.host}:5432/warehouse2`
  )
})

test("something that is not an address is refused, and nothing changes", async ({
  page,
}) => {
  await login(page)
  await pickAdapterType(page, "postgres")
  await page.getByTestId("field-database").fill("warehouse")

  await typeUrl(page, "just some text")

  // Said on the field that was typed into, not as a toast over the window: it
  // is that text that is wrong.
  await expect(page.getByText("not a PostgreSQL connection string")).toBeVisible()
  await expect(page.getByTestId("field-database")).toHaveValue("warehouse")
})
