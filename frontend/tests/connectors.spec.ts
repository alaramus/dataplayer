import { expect, test } from "@playwright/test"

import { DATABASE } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorAction, connectorRow } from "./utils/workspace"


// Quasar forwards data-testid onto the input element, so field ids address the
// input directly, without a nested locator.
async function fillConnectionFields(
  page: import("@playwright/test").Page,
  password: string
) {
  await page.getByTestId("connector-type").click()
  await page.getByRole("option", { name: "PostgreSQL" }).click()

  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(password)
}

test("creates a connection, checks it and deletes it", async ({ page }) => {
  const name = `e2e-postgres-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)

  await page.getByTestId("check-draft").click()
  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-positive/)

  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await connectorAction(page, name, "check")
  await expect(page.locator(".q-notification").first()).toBeVisible()

  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a wrong password reports an auth failure without leaking the password", async ({
  page,
}) => {
  const wrongPassword = "definitely-not-the-password"
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(`e2e-bad-${Date.now()}`)
  await fillConnectionFields(page, wrongPassword)

  await page.getByTestId("check-draft").click()

  const result = page.getByTestId("check-result")
  await expect(result).toBeVisible()
  await expect(result).toHaveClass(/bg-negative/)
  await expect(result).toContainText("Authentication failed")
  await expect(result).not.toContainText(wrongPassword)
})

test("the secret field is empty while editing and needs no retyping", async ({
  page,
}) => {
  const name = `e2e-edit-${Date.now()}`
  await login(page)

  await page.getByTestId("add-connector").click()
  await page.getByTestId("connector-name").fill(name)
  await fillConnectionFields(page, DATABASE.password)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await connectorAction(page, name, "edit")
  await expect(page.getByTestId("field-password")).toHaveValue("")

  // The password is left blank: the server substitutes the stored one by
  // connector_id.
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toHaveClass(/bg-positive/)

  await page.getByRole("button", { name: "Cancel" }).click()
  await connectorAction(page, name, "delete")
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})
