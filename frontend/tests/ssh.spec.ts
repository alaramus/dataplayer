import { expect, test } from "@playwright/test"

import { pickAdapterType } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector } from "./utils/workspace"

/**
 * An SSH server as a source, and the keys a person signs in with (D144–D147).
 *
 * Against `sshd` from compose.override.yml, as the backend container sees it:
 * the check and every read run on the server. The connection signs in with
 * the password — a key made here would have to be added to the server's
 * authorized_keys first, which a browser cannot do, and the backend suite
 * signs in with one.
 */
const SERVER = { host: "sshd", port: "2222", user: "dataplayer", password: "dataplayer" }

test("a key is made on the Preferences page, and only its public half is shown", async ({
  page,
}) => {
  const name = `e2e-key-${Date.now()}`
  await login(page)
  await page.goto("/preferences")

  await page.getByTestId("ssh-key-new").click()
  await page.getByTestId("ssh-key-name").fill(name)
  await page.getByTestId("ssh-key-save").click()

  const row = page.getByTestId(`ssh-key-${name}`)
  await expect(row).toContainText("ssh-ed25519")
  await expect(row).toContainText("No passphrase")
  // The private half never came back from the server, so it cannot be here.
  await expect(page.getByTestId("ssh-keys")).not.toContainText("PRIVATE KEY")

  await page.getByTestId(`ssh-key-delete-${name}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0)
})

test("an SSH server is trusted by its key before anything is sent, and then browsed", async ({
  page,
}) => {
  const name = `e2e-ssh-${Date.now()}`
  await login(page)
  await pickAdapterType(page, "ssh")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(SERVER.host)
  await page.getByTestId("field-port").fill(SERVER.port)
  await page.getByTestId("field-username").fill(SERVER.user)
  await page.getByTestId("field-auth_method").click()
  await page.getByRole("option", { name: "Password", exact: true }).click()
  await page.getByTestId("field-password").fill(SERVER.password)

  // Nothing connects before the server's key is trusted (D145).
  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toContainText("confirm")

  await page.getByTestId("server-key-fetch").click()
  await expect(page.getByTestId("server-key-presented")).toContainText("SHA256:")
  await page.getByTestId("server-key-trust").click()
  await expect(page.getByTestId("server-key-pinned")).toContainText("SHA256:")

  await page.getByTestId("check-draft").click()
  await expect(page.getByTestId("check-result")).toContainText("Connection successful")
  await page.getByTestId("save-connector").click()

  await connectorRow(page, name).click()
  // The user's home on the development server holds the server's own logs.
  await expect(page.getByTestId("catalog-list")).toContainText("logs")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
