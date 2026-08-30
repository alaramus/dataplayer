import { expect, test } from "@playwright/test"

import {
  catalogAction,
  catalogCheck,
  catalogRow,
  openNode,
  pickSchema,
  showOnlySchema,
} from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test("creates, fills, renames and removes a folder in personal storage", async ({
  page,
}) => {
  const name = `e2e-actions-${Date.now()}`
  const folder = `batch-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("reports")

  // Nothing ticked: the menu keeps its shape and greys out everything that
  // would change a node. Standing in a folder is not choosing it, so nothing
  // here can rename or remove the folder being looked at.
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-create_folder")).toBeVisible()
  await expect(page.getByTestId("menu-item-upload")).toBeVisible()
  await expect(page.getByTestId("menu-item-delete")).toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await expect(page.getByTestId("menu-item-rename")).toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await page.keyboard.press("Escape")

  // --- create a folder, and see it appear without reopening the dialog
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText(folder)

  // --- upload a file into it. The folder is walked into, not ticked: an
  // upload belongs to the directory one is looking at.
  await openNode(page, folder)
  await catalogAction(page, "upload")
  // Quasar puts data-testid on the input itself, so it is addressed directly.
  await page.getByTestId("action-file").setInputFiles({
    name: "uploaded.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,name\n1,one\n2,two\n"),
  })
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("uploaded.csv")

  // --- what was uploaded is readable, which proves the bytes arrived whole
  await openNode(page, "uploaded.csv")
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("name")
  await expect(grid.locator("tbody tr")).toHaveCount(2)

  // --- rename it. Ticking picks it out without opening it again.
  await catalogCheck(page, "uploaded.csv").click()
  await catalogAction(page, "rename")
  await page
    .getByTestId("action-dialog")
    .getByRole("textbox")
    .first()
    .fill("renamed.csv")
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("renamed.csv")
  await expect(list).not.toContainText("uploaded.csv")

  // --- a folder with something inside refuses to go quietly
  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await expect(page.getByTestId("action-warning")).toContainText("cannot be undone")
  await page.getByTestId("action-submit").click()
  await expect(page.getByTestId("action-error")).toContainText("not empty")

  // --- saying so explicitly removes it
  await page.getByTestId("field-recursive").click()
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("two files at once admit only what can be done to many", async ({ page }) => {
  const name = `e2e-bulk-${Date.now()}`
  const first = `bulk-a-${Date.now()}`
  const second = `bulk-b-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  for (const folder of [first, second]) {
    await catalogAction(page, "create_folder")
    await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
    await page.getByTestId("action-submit").click()
    await expect(page.getByTestId("catalog-list")).toContainText(folder)
  }

  await catalogCheck(page, first).click()
  await catalogCheck(page, second).click()

  // Renaming two folders to one name is not two renames, and the action says
  // so itself — the server marks it as not applying to the set.
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-delete")).not.toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await expect(page.getByTestId("menu-item-rename")).toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await page.getByTestId("menu-item-delete").click()

  await page.getByTestId("action-submit").click()
  // One line for the whole set, and both are gone.
  await expect(page.locator(".q-notification", { hasText: "2 of 2" })).toBeVisible()
  await expect(catalogRow(page, first)).toHaveCount(0)
  await expect(catalogRow(page, second)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("renames a relation without leaving its schema", async ({ page }) => {
  const name = `e2e-actions-pg-${Date.now()}`
  const renamed = `audit_events_${Date.now()}`
  await login(page)

  await createPostgresConnector(page, name)

  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await expect(catalogRow(page, "audit_events")).toBeVisible()

  await catalogCheck(page, "audit_events").click()
  await catalogAction(page, "rename_relation")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(renamed)
  await page.getByTestId("action-submit").click()

  // Reloading the root must keep the grouping that contained the relation;
  // otherwise the catalog silently falls back to `public` after the rename.
  await expect(catalogRow(page, renamed)).toBeVisible()
  await expect(page.getByTestId("catalog-groups")).toContainText("demo_lab")
  await expect(page.getByTestId("catalog-error")).toHaveCount(0)

  // Leave the shared fixture exactly as the next scenario expects it.
  await catalogCheck(page, renamed).click()
  await catalogAction(page, "rename_relation")
  await page
    .getByTestId("action-dialog")
    .getByRole("textbox")
    .first()
    .fill("audit_events")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, "audit_events")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("loads a CSV into the schema being looked at", async ({ page }) => {
  const name = `e2e-load-csv-${Date.now()}`
  // Unique, because nothing here drops a relation yet: the fixture schema is
  // rebuilt from sql/ on every `docker compose up`, and until then a rerun
  // must not collide with what the last one made.
  const table = `loaded_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  // One schema on, because one file makes one table: with two places ticked
  // the action greys out the way renaming two folders does.
  await showOnlySchema(page, "demo_lab", "public")
  // By the grouping rather than by a table in it: the scenario above renames
  // one while this runs, and the schema is what this test is standing in.
  await expect(page.getByTestId("catalog-groups")).toContainText("demo_lab")

  // The button is in the menu because the source declares the action; nothing
  // in the catalog knows what PostgreSQL is.
  await page.getByTestId("catalog-actions").click()
  await expect(page.getByTestId("menu-item-load_csv")).not.toHaveAttribute(
    "aria-disabled",
    "true"
  )
  await page.keyboard.press("Escape")

  await catalogAction(page, "load_csv")
  await expect(page.getByTestId("action-dialog")).toContainText("demo_lab")
  await page.getByTestId("action-file").setInputFiles({
    name: "regions.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("code,label\nEU,Europe\nUS,United States\n"),
  })
  await page.getByTestId("field-name").fill(table)
  await page.getByTestId("action-submit").click()

  // The schema is what gained a child, and the list says so without a reload.
  await expect(page.getByTestId("catalog-list")).toContainText(table)

  // Reading it back proves the rows arrived, with the header as the columns.
  await openNode(page, table)
  const grid = page.getByTestId("row-grid")
  await expect(grid).toContainText("label")
  await expect(grid.locator("tbody tr")).toHaveCount(2)
  await expect(page.getByTestId("grid-cell-0-label")).toHaveText("Europe")

  // --- and it can be dropped again, which is how this leaves nothing behind
  await catalogCheck(page, table).click()
  await catalogAction(page, "drop_relation")
  await expect(page.getByTestId("action-preview")).toContainText("Nothing else")
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, table)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("shows what a cascade would take before dropping anything", async ({ page }) => {
  const name = `e2e-drop-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await showOnlySchema(page, "demo_lab", "public")

  // A table with a view built on it, which is the case the preview exists for.
  await catalogCheck(page, "projects").click()
  await catalogAction(page, "drop_relation")

  // Asked before anything is ticked in the form: without a cascade the source
  // refuses, and says what is in the way. The button follows that answer.
  const preview = page.getByTestId("action-preview")
  await expect(preview).toContainText("project_rollup")
  await expect(page.getByTestId("action-submit")).toBeDisabled()

  // Ticking the box asks again, and the answer changes.
  await page.getByTestId("field-cascade").click()
  await expect(preview).toContainText("project_rollup")
  await expect(page.getByTestId("action-submit")).toBeEnabled()

  // Nothing is dropped here: the rehearsal was rolled back, and so is this.
  await page.getByRole("button", { name: "Cancel" }).click()
  await expect(catalogRow(page, "projects")).toBeVisible()
  await expect(catalogRow(page, "project_rollup")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
