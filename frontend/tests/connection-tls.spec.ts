import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { DATABASE, pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, editConnector } from "./utils/workspace"

/**
 * The TLS page of the connection window (D446): its own page, its mode and
 * trust offered by name, a CA certificate it cannot read refused on the field,
 * a card that starts somewhere sensible, a choice kept once saved, a
 * certificate read from the file it lives in rather than pasted.
 */

async function choose(page: Page, field: string, label: string) {
  await page.getByTestId(`field-${field}`).click()
  await page.getByRole("option", { name: label, exact: true }).click()
}

test("a CA certificate the TLS page cannot read is refused on the field", async ({ page }) => {
  await login(page)
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(`e2e-tls-${Date.now()}`)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)

  await page.getByTestId("connector-tabs-tls").click()
  await choose(page, "tls_mode", "Verify full")
  await choose(page, "tls_trust", "A CA certificate")
  await page.getByTestId("field-tls_ca_certificate").fill("not a certificate")
  await page.getByTestId("save-connector").click()

  await expect(page.getByText("Paste a certificate in PEM, BEGIN CERTIFICATE and all")).toBeVisible()
})

test("a CA certificate is read from its file into the field", async ({ page }) => {
  const pem = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"
  await login(page)
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-tabs-tls").click()
  await choose(page, "tls_mode", "Verify full")
  await choose(page, "tls_trust", "A CA certificate")

  const chooser = page.waitForEvent("filechooser")
  await page.getByTestId("field-tls_ca_certificate-from-file").click()
  await (await chooser).setFiles({ name: "ca.pem", mimeType: "application/x-pem-file", buffer: Buffer.from(pem) })

  await expect(page.getByTestId("field-tls_ca_certificate")).toHaveValue(pem)
})

test("the Amazon RDS card starts at Verify full against Amazon RDS's authorities", async ({ page }) => {
  await login(page)
  await pickAdapterType(page, "aws-rds-postgres")

  await page.getByTestId("connector-tabs-tls").click()

  await expect(page.getByTestId("field-tls_mode")).toHaveValue("Verify full")
  await expect(page.getByTestId("field-tls_trust")).toHaveValue("Amazon RDS")
})

test("a mode chosen on the TLS page is kept when the connection is saved", async ({ page }) => {
  const name = `e2e-tls-kept-${Date.now()}`
  await login(page)
  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)
  await page.getByTestId("connector-tabs-tls").click()
  // The development database speaks no TLS, so Off is the mode that connects.
  await choose(page, "tls_mode", "Off")
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()

  await editConnector(page, name)
  await page.getByTestId("connector-tabs-tls").click()
  await expect(page.getByTestId("field-tls_mode")).toHaveValue("Off")
  await page.keyboard.press("Escape")

  await deleteConnector(page, name)
})
