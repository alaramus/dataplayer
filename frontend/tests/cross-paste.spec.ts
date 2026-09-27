import { expect, test } from "@playwright/test"

import {
  catalogAction,
  catalogCheck,
  catalogRow,
  openNode,
  pickSchema,
  showOnlySchema,
} from "./utils/catalog"
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

test("saves several tables as one CSV file each, and asks once about taken names", async ({
  page,
}) => {
  const database = `e2e-several-db-${Date.now()}`
  const files = `e2e-several-files-${Date.now()}`
  const folder = `e2e-several-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  await openConnector(page, files)
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toBeVisible()

  await openConnector(page, database)
  await pickSchema(page, "demo_lab")
  await catalogCheck(page, "projects").click()
  await catalogCheck(page, "teams").click()
  await catalogAction(page, "client:copy")

  // Named after themselves, so no window asks for a name (D171).
  await openConnector(page, files)
  await openNode(page, folder)
  await catalogAction(page, "client:cross-paste")
  await expect(page.getByTestId("cross-paste-name")).toHaveCount(0)
  await expect(catalogRow(page, "projects.csv")).toBeVisible()
  await expect(catalogRow(page, "teams.csv")).toBeVisible()

  // Both names are taken now; the window asks once, for both.
  await catalogAction(page, "client:cross-paste")
  const conflict = page.getByTestId("cross-paste-conflict")
  await expect(conflict).toContainText("projects.csv and 1 other file are already there")
  await page.getByTestId("cross-paste-keep-both").click()
  await expect(catalogRow(page, "projects (1).csv")).toBeVisible()
  await expect(catalogRow(page, "teams (1).csv")).toBeVisible()

  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)
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

  // It ran as a job the server owns. Ended, it is one entry in Recent with
  // both connections and what became of each file (D168, D181), and it has
  // left Working.
  await page.getByTestId("activity-indicator").click()
  const transfer = page.getByTestId("recent-section").getByTestId("notice").filter({
    hasText: `Copy files · ${files} → ${server}`,
  })
  await expect(transfer).toHaveCount(1)
  await expect(transfer).toContainText(`${file} — copied`)
  await expect(page.getByTestId("working-section")).not.toContainText(`Copy files · ${files} → ${server}`)
  await page.getByTestId("activity-indicator").click()

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

test("pastes a CSV into a database as a new table, then adds its rows to that table", async ({
  page,
}) => {
  const database = `e2e-rows-db-${Date.now()}`
  const files = `e2e-rows-files-${Date.now()}`
  const csv = `e2e-rows-${Date.now()}.csv`
  // Named per run: the fixture schema is rebuilt on `docker compose up`, not
  // between runs.
  const table = `pasted_rows_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  await openConnector(page, files)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: csv,
    mimeType: "text/csv",
    buffer: Buffer.from("id,name\n1,Ada\n2,Grace\n"),
  })
  await page.getByTestId("action-submit").click()
  await catalogCheck(page, csv).click()
  await catalogAction(page, "client:copy")

  // A new table: D45's form, with the connection and schema already decided
  // by where Paste was chosen (D166).
  await openConnector(page, database)
  await showOnlySchema(page, "demo_lab")
  await catalogAction(page, "client:cross-paste")
  await expect(page.getByTestId("grid-create-table-connector")).toHaveCount(0)
  await page.getByTestId("grid-create-table-name").fill(table)
  await page.getByTestId("grid-create-table-run").click()
  await expect(catalogRow(page, table)).toBeVisible()

  // With that table ticked there are two answers, and the list asks which.
  const box = catalogCheck(page, table)
  if (!(await box.isChecked())) await box.click()
  await catalogAction(page, "client:cross-paste")
  await expect(page.getByTestId("cross-paste-offer-rows_new_relation")).toBeVisible()
  await page.getByTestId("cross-paste-offer-rows_into_relation").click()
  // Same names are paired to start with, so the rows can go straight in.
  await page.getByTestId("grid-import-run").click()
  await expect(page.getByTestId("grid-import-dialog")).toHaveCount(0)

  await openNode(page, table)
  await expect(page.getByTestId("row-grid").locator("tbody tr")).toHaveCount(4)

  if (!(await box.isChecked())) await box.click()
  await catalogAction(page, "drop_relation")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, table)).toHaveCount(0)

  await openConnector(page, files)
  const copied = catalogCheck(page, csv)
  if (!(await copied.isChecked())) await copied.click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, csv)).toHaveCount(0)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})

test("carries a folder whole to an SSH server and moves it back", async ({ page }) => {
  const files = `e2e-folder-files-${Date.now()}`
  const server = `e2e-folder-ssh-${Date.now()}`
  const folder = `e2e-folder-${Date.now()}`
  const file = `inside-${Date.now()}.txt`
  await login(page)
  await createFileConnector(page, files)
  await createSshConnector(page, server)

  await openConnector(page, files)
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await openNode(page, folder)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles({
    name: file,
    mimeType: "text/plain",
    buffer: Buffer.from("inside a folder\n"),
  })
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, file)).toBeVisible()
  await page.getByTestId("catalog-up").click()

  // A ticked folder is copied whole, with what is inside it (D169).
  await catalogCheck(page, folder).click()
  await catalogAction(page, "client:copy")
  await openConnector(page, server)
  await catalogAction(page, "client:cross-paste")
  await expect(catalogRow(page, folder)).toBeVisible()
  await openNode(page, folder)
  await expect(catalogRow(page, file)).toBeVisible()
  await page.getByTestId("catalog-up").click()

  // Cut it on the server and paste it into reports at home: the server's copy
  // goes once everything has arrived.
  await catalogCheck(page, folder).click()
  await catalogAction(page, "client:cut")
  await openConnector(page, files)
  await openNode(page, "reports")
  await catalogAction(page, "client:cross-paste")
  await expect(catalogRow(page, folder)).toBeVisible()
  await openConnector(page, server)
  await expect(page.getByTestId("catalog-list")).not.toContainText(folder)

  await openConnector(page, files)
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)
  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, server)
  await deleteConnector(page, files)
})
