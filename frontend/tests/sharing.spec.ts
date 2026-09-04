import { expect, test } from "@playwright/test"

import { createPostgresConnector, openPermissions } from "./utils/connectors"
import { firstSuperuser } from "./config"
import {
  COLLEAGUE_PASSWORD,
  colleagueEmail,
  createColleague,
  removeColleague,
  signInAs,
  signOut,
} from "./utils/people"
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
  await openPermissions(page)
  await page.getByTestId("share-connector").click()
  await page.getByTestId("share-user").click()
  await page.getByRole("option", { name: email }).click()
  await expectFieldActionAligned(
    page.getByTestId("share-level"),
    page.getByTestId("share-submit")
  )
  await page.getByTestId("share-submit").click()
  await page.getByTestId("share-close").click()
  // The list is on the page and not behind the button: closing the dialog
  // leaves the connection's own window showing who now holds a level.
  await expect(page.getByTestId(`share-row-${email}`)).toBeVisible()
  await page.getByTestId("cancel-connector").click()

  // --- the colleague finds it ----------------------------------------------
  await signOut(page)
  await signInAs(page, email, COLLEAGUE_PASSWORD)
  await expect(connectorRow(page, name)).toBeVisible()

  await editConnector(page, name)
  // A grant is access to the source, not to the record of how to reach it:
  // the options are shown, and none of them can be touched.
  await expect(page.getByTestId("connector-name")).toBeDisabled()
  await expect(page.getByTestId("connector-enabled")).toBeDisabled()
  await expect(page.getByTestId("field-host")).toBeDisabled()
  await expect(page.getByTestId("save-connector")).toHaveCount(0)
  await expect(page.getByTestId("apply-connector")).toHaveCount(0)
  await expect(page.getByTestId("delete-connector")).toHaveCount(0)

  // Whose it is and what was given, on the page that answers exactly that.
  // Nothing on it to change: a level does not pass on the right to widen it,
  // and how far a console may go is the owner's alone (D66).
  await openPermissions(page)
  await expect(page.getByTestId("connector-shared")).toContainText("Shared by")
  await expect(page.getByTestId("connector-policy")).toHaveCount(0)
  await expect(page.getByTestId("share-connector")).toHaveCount(0)
  await page.getByTestId("cancel-connector").click()

  // --- and loses it when it is taken back ----------------------------------
  await signOut(page)
  await login(page)
  await editConnector(page, name)
  // Taking it back is on the page too: the row is there, and so is the cross.
  await openPermissions(page)
  await page.getByTestId(`share-revoke-${email}`).click()
  await expect(page.getByTestId(`share-row-${email}`)).toHaveCount(0)
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
  // The old address still works, and lands where accounts live now.
  await page.goto("/users")
  await page.waitForURL("/admin/users")
  await expect(
    page.getByText("Only an administrator manages this installation")
  ).toBeVisible()

  await signOut(page)
  await login(page)
  await removeColleague(page, email)
})

test("an administrator is not offered a way to delete their own account", async ({
  page,
}) => {
  await login(page)
  await page.getByTestId("open-users").click()
  await page.waitForURL("/admin")
  await expect(page.getByTestId("admin-section-users")).toBeVisible()

  // The server refuses it; the button says so before it is pressed.
  await expect(page.getByTestId(`delete-user-${firstSuperuser}`)).toBeDisabled()
})
