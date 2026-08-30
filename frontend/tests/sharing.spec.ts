import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { firstSuperuser } from "./config"
import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"
import { connectorRow, editConnector } from "./utils/workspace"

/**
 * Sharing a connection with a colleague, end to end.
 *
 * The one scenario that cannot be proved anywhere else: it needs two accounts,
 * two sessions and the screen each of them gets. Everything about levels is
 * settled by the backend tests; what is checked here is that the person the
 * connection was shared with sees it, and sees it as somebody else's.
 */
const COLLEAGUE_PASSWORD = "shared-access-1"

function colleagueEmail(): string {
  return `colleague-${Date.now()}@example.com`
}

async function signInAs(page: Page, email: string, password: string) {
  await page.goto("/login")
  await page.getByTestId("login-email").fill(email)
  await page.getByTestId("login-password").fill(password)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}

async function signOut(page: Page) {
  await page.getByTestId("logout").click()
  await page.waitForURL("/login")
}

async function createColleague(page: Page, email: string) {
  await page.getByTestId("open-users").click()
  await page.waitForURL("/users")
  await page.getByTestId("new-user").click()
  await page.getByTestId("user-email").fill(email)
  await page.getByTestId("user-password").fill(COLLEAGUE_PASSWORD)
  await page.getByTestId("user-save").click()
  await expect(page.getByTestId(`edit-user-${email}`)).toBeVisible()
  await page.getByTestId("back-to-workspace").click()
  await page.waitForURL("/")
}

async function removeColleague(page: Page, email: string) {
  await page.getByTestId("open-users").click()
  await page.waitForURL("/users")
  await page.getByTestId(`delete-user-${email}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(page.getByTestId(`edit-user-${email}`)).toHaveCount(0)
}

test("a shared connection appears for the colleague and stays the owner's", async ({
  page,
}) => {
  const email = colleagueEmail()
  const name = `shared ${Date.now()}`

  await login(page)
  await createColleague(page, email)
  await createPostgresConnector(page, name)

  // --- the owner hands it over ---------------------------------------------
  await editConnector(page, name)
  await page.getByTestId("share-connector").click()
  await page.getByTestId("share-user").click()
  await page.getByRole("option", { name: email }).click()
  await expectFieldActionAligned(
    page.getByTestId("share-level"),
    page.getByTestId("share-submit")
  )
  await page.getByTestId("share-submit").click()
  await expect(page.getByTestId(`share-row-${email}`)).toBeVisible()
  await page.getByTestId("share-close").click()
  await page.getByTestId("cancel-connector").click()

  // --- the colleague finds it ----------------------------------------------
  await signOut(page)
  await signInAs(page, email, COLLEAGUE_PASSWORD)
  await expect(connectorRow(page, name)).toBeVisible()

  await editConnector(page, name)
  // Whose it is, said in the window rather than left to be worked out.
  await expect(page.getByTestId("connector-shared")).toContainText("Shared by")
  // A grant is access to the source, not to the record of how to reach it:
  // the options are shown, and none of them can be touched.
  await expect(page.getByTestId("connector-name")).toBeDisabled()
  await expect(page.getByTestId("connector-enabled")).toBeDisabled()
  await expect(page.getByTestId("field-host")).toBeDisabled()
  await expect(page.getByTestId("save-connector")).toHaveCount(0)
  await expect(page.getByTestId("apply-connector")).toHaveCount(0)
  await expect(page.getByTestId("delete-connector")).toHaveCount(0)
  await expect(page.getByTestId("share-connector")).toHaveCount(0)
  await page.getByTestId("cancel-connector").click()

  // --- and loses it when it is taken back ----------------------------------
  await signOut(page)
  await login(page)
  await editConnector(page, name)
  await page.getByTestId("share-connector").click()
  await page.getByTestId(`share-revoke-${email}`).click()
  await expect(page.getByTestId(`share-row-${email}`)).toHaveCount(0)
  await page.getByTestId("share-close").click()
  await page.getByTestId("cancel-connector").click()

  await signOut(page)
  await signInAs(page, email, COLLEAGUE_PASSWORD)
  await expect(connectorRow(page, name)).toHaveCount(0)

  // --- clean up after ourselves --------------------------------------------
  await signOut(page)
  await login(page)
  await page.locator(`[data-testid="connector-edit-${name}"]`).click()
  await page.locator('[data-testid="delete-connector"][tabindex="0"]').click()
  await page.getByTestId("confirm-accept").click()
  await removeColleague(page, email)
})

test("the accounts screen is an administrator's", async ({ page }) => {
  const email = colleagueEmail()

  await login(page)
  await createColleague(page, email)

  await signOut(page)
  await signInAs(page, email, COLLEAGUE_PASSWORD)

  // Not offered, because the routes behind it would refuse.
  await expect(page.getByTestId("open-users")).toHaveCount(0)
  await page.goto("/users")
  await expect(page.getByText("Only an administrator manages accounts")).toBeVisible()

  await signOut(page)
  await login(page)
  await removeColleague(page, email)
})

test("an administrator is not offered a way to delete their own account", async ({
  page,
}) => {
  await login(page)
  await page.getByTestId("open-users").click()
  await page.waitForURL("/users")

  // The server refuses it; the button says so before it is pressed.
  await expect(page.getByTestId(`delete-user-${firstSuperuser}`)).toBeDisabled()
})
