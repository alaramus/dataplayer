import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode } from "./utils/catalog"
import { createFileConnector, fillSshServer } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

/**
 * An SSH server as a source, and the keys a person signs in with (D144–D147).
 *
 * Against `sshd` from compose.override.yml, as the backend container sees it:
 * the check and every read run on the server. The connection signs in with
 * the password; the backend suite signs in with a key.
 */

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
  await fillSshServer(page, name)

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
  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("logs")

  // The file explorer over SFTP (D150): a CSV sent to the server opens as
  // rows, which the SSH source could not do before it was one.
  const folder = `e2e-ssh-${Date.now()}`
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText(folder)
  await openNode(page, folder)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: "sales.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,region\n1,north\n2,south\n"),
  })
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("sales.csv")
  await openNode(page, "sales.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("region")
  await expect(grid.locator("tbody tr")).toHaveCount(2)

  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a viewer that finds the key locked offers to unlock it, and reads again once it is", async ({
  page,
}) => {
  const name = `e2e-locked-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  // The refusal and the key are the server's answers, stood in for here: a
  // real locked key needs one the development server trusts, and what is
  // under test is what every screen does with the answer (D147).
  let locked = true
  let connectorId = ""
  const key = {
    id: "e2e-locked-key",
    name: "e2e",
    algorithm: "ssh-ed25519",
    public_key: "ssh-ed25519 AAAA dataplayer",
    fingerprint: "SHA256:e2e",
    passphrase_mode: "ask",
    unlocked_until: null,
    created_at: null,
  }
  const usedBy = () => [{ id: connectorId, name }]
  await page.route(
    (url) => /\/api\/v1\/connectors\/[^/]+\/(content|fetch)$/.test(url.pathname),
    async (route) => {
      connectorId = new URL(route.request().url()).pathname.split("/")[4] ?? ""
      if (!locked) {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            message: "The SSH key e2e is locked; enter its passphrase to use it",
            error_kind: "locked",
          },
        }),
      })
    }
  )
  await page.route(
    (url) => url.pathname === "/api/v1/ssh-keys/",
    async (route) => {
      await route.fulfill({ json: [{ ...key, used_by: usedBy() }] })
    }
  )
  await page.route(
    (url) => url.pathname === `/api/v1/ssh-keys/${key.id}/unlock`,
    async (route) => {
      locked = false
      await route.fulfill({
        json: {
          ...key,
          unlocked_until: new Date(Date.now() + 15 * 60_000).toISOString(),
          used_by: usedBy(),
        },
      })
    }
  )

  // A recording and a table, each with the way on beside what went wrong.
  await openNode(page, "tone.wav")
  const media = page.getByTestId("content-error")
  await expect(media).toContainText("is locked")
  await expect(media.getByTestId("unlock-key")).toBeVisible()
  await openNode(page, "sample.csv")
  const grid = page.getByTestId("grid-error")
  await expect(grid).toContainText("is locked")
  await grid.getByTestId("unlock-key").click()

  await page.getByTestId("unlock-key-passphrase").fill("held a while")
  await page.getByTestId("unlock-key-confirm").click()

  // Unlocking reads again what failed for want of the key, the other tab too.
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await openNode(page, "tone.wav")
  await expect(page.getByTestId("media-details")).toContainText("WAV")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
