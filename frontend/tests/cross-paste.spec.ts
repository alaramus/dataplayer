import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode, pickSchema } from "./utils/catalog"
import {
  createFileConnector,
  createPostgresConnector,
  createSshConnector,
} from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

// Paste of a clipboard held in another connection (D164). The file source's
// personal directory holds `reports` once `app.seed_storage` has run, and the
// development SSH server is `sshd` from compose.override.yml.

test("saves a database table as a CSV file in a folder of another connection", async ({
  page,
}) => {
  const database = `e2e-paste-db-${Date.now()}`
  const files = `e2e-paste-files-${Date.now()}`
  const saved = `e2e-projects-${Date.now()}.csv`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  // A table can be copied out and never cut: pasting it elsewhere does not
  // remove it (D165).
  await openConnector(page, database)
  await pickSchema(page, "demo_lab")
  await catalogCheck(page, "projects").click()
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-client:copy")).not.toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await expect(page.getByTestId("menu-item-client:cut")).toHaveCount(0)
  await page.getByTestId("menu-item-client:copy").click()

  // A conversion asks for the name of what it makes before anything is sent.
  await openConnector(page, files)
  await openNode(page, "reports")
  await catalogAction(page, "client:cross-paste")
  const name = page.getByTestId("cross-paste-file-name")
  await expect(name).toHaveValue("projects.csv")
  await name.fill(saved)
  await page.getByTestId("cross-paste-save").click()
  await expect(page.getByTestId("cross-paste-name")).toHaveCount(0)
  await expect(catalogRow(page, saved)).toBeVisible()

  // It opens as rows, like any CSV in the folder.
  await openNode(page, saved)
  await expect(page.getByTestId("row-grid")).toContainText("budget")

  await catalogCheck(page, saved).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, saved)).toHaveCount(0)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("copies a file to an SSH server and moves it back", async ({ page }) => {
  const files = `e2e-cross-files-${Date.now()}`
  const server = `e2e-cross-ssh-${Date.now()}`
  const folder = `e2e-cross-${Date.now()}`
  const file = `e2e-cross-${Date.now()}.txt`
  await login(page)
  await createFileConnector(page, files)
  await createSshConnector(page, server)

  await openConnector(page, files)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: file,
    mimeType: "text/plain",
    buffer: Buffer.from("across connections\n"),
  })
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, file)).toBeVisible()
  await catalogCheck(page, file).click()
  await catalogAction(page, "client:copy")

  // A plain copy runs straight from the menu, with no window in between.
  await openConnector(page, server)
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await openNode(page, folder)
  await catalogAction(page, "client:cross-paste")
  await expect(catalogRow(page, file)).toBeVisible()

  // Cut on the server, Paste back home: the file leaves the server, and the
  // server's catalog says so without being reloaded by hand.
  await catalogCheck(page, file).click()
  await catalogAction(page, "client:cut")
  await openConnector(page, files)
  await openNode(page, "reports")
  await catalogAction(page, "client:cross-paste")
  await expect(catalogRow(page, file)).toBeVisible()
  await openConnector(page, server)
  await expect(page.getByTestId("catalog-list")).not.toContainText(file)

  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await openConnector(page, files)
  await catalogCheck(page, file).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, file)).toHaveCount(0)
  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, file).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, file)).toHaveCount(0)

  await deleteConnector(page, server)
  await deleteConnector(page, files)
})
