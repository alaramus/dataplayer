import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import {
  addFilter,
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
import { toast } from "./utils/notices"

/** A small table in the schema being looked at, made through the source's own action. */
async function loadCsv(page: Page, table: string) {
  await catalogAction(page, "load_csv")
  await page.getByTestId("load-file").setInputFiles({
    name: `${table}.csv`,
    mimeType: "text/csv",
    buffer: Buffer.from("code,label\nEU,Europe\n"),
  })
  await page.getByTestId("field-name").fill(table)
  await page.getByTestId("load-create").click()
  await expect(page.getByTestId("catalog-list")).toContainText(table)
}

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
  // And each greyed line says what would make it usable, on hover. Whether a
  // tooltip opens over a disabled item is a question about pointer events
  // that only a browser answers: a unit test can see the text is there and
  // not that anybody can reach it.
  await page.getByTestId("menu-item-rename").hover()
  await expect(page.locator(".q-tooltip")).toContainText("Tick a row to use this")
  await page.keyboard.press("Escape")

  // --- create a folder, and see it appear without reopening the dialog
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(list).toContainText(folder)

  // --- upload files into it. The folder is walked into, not ticked: an
  // upload belongs to the directory one is looking at.
  await openNode(page, folder)
  await catalogAction(page, "upload")
  // Quasar puts data-testid on the input itself, so it is addressed directly.
  await page.getByTestId("action-file").setInputFiles([
    {
      name: "uploaded.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,name\n1,one\n2,two\n"),
    },
    {
      name: "notes.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# hi\n"),
    },
    {
      name: "dropped.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("no\n"),
    },
  ])

  // Choosing stages the files and sends nothing, so the list is still the
  // place to change one's mind: a row taken out never leaves the browser.
  const staged = page.getByTestId("action-files")
  await expect(staged).toContainText("dropped.txt")
  await expect(list).not.toContainText("uploaded.csv")
  await page.getByTestId("action-file-remove-2").click()
  await expect(staged).not.toContainText("dropped.txt")

  await page.getByTestId("action-submit").click()
  await expect(list).toContainText("uploaded.csv")
  await expect(list).toContainText("notes.md")
  await expect(list).not.toContainText("dropped.txt")

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

  // --- one destructive confirmation removes the folder and its contents
  await page.getByTestId("catalog-up").click()
  await catalogCheck(page, folder).click()
  await catalogAction(page, "delete")
  await expect(page.getByTestId("action-confirmation")).toHaveText(
    `Are you sure you want to delete ${folder}?`
  )
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, folder)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens a second action beside the first rather than over it", async ({
  page,
}) => {
  const name = `e2e-two-forms-${Date.now()}`
  const folder = `two-forms-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)

  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill(folder)
  await page.getByTestId("action-submit").click()
  await expect(page.getByTestId("catalog-list")).toContainText(folder)

  // How many forms are worth having open is the user's decision: a second one
  // is a second window, and the first keeps whatever was typed into it.
  await catalogAction(page, "create_folder")
  await page.getByTestId("action-dialog").getByRole("textbox").first().fill("kept")
  await catalogCheck(page, folder).click()
  await catalogAction(page, "rename")
  await expect(page.getByTestId("action-dialog")).toHaveCount(2)
  await expect(
    page.getByTestId("action-dialog").first().getByRole("textbox").first()
  ).toHaveValue("kept")

  // And the same line twice is one window, not a pile of identical forms.
  await catalogAction(page, "rename")
  await expect(page.getByTestId("action-dialog")).toHaveCount(2)

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
  // The head of the level counts twice: what is here, and how much of it the
  // menu below would be applied to.
  await expect(page.getByTestId("catalog-count")).toContainText("(2 selected)")

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
  await expect(toast(page, "2 of 2")).toBeVisible()
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
  const renameInput = page.getByTestId("action-dialog").getByRole("textbox").first()
  await expect(renameInput).toHaveValue("audit_events")
  await renameInput.fill(renamed)
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

test("creates and renames a schema, moves a relation, then drops the schema", async ({
  page,
}) => {
  const connector = `e2e-schema-${Date.now()}`
  const created = `stage_${Date.now()}`
  const renamed = `archive_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, connector)
  await openConnector(page, connector)

  // A schema belongs to the database level, not inside whichever schema is
  // currently filtering the rows below it.
  await catalogAction(page, "create_schema")
  await page.getByTestId("field-name").fill(created)
  await page.getByTestId("action-submit").click()

  await showOnlySchema(page, created)
  await catalogAction(page, "rename_schema")
  const rename = page.getByTestId("field-new_name")
  await expect(rename).toHaveValue(created)
  await rename.fill(renamed)
  await page.getByTestId("action-submit").click()
  // The grouping follows the exact replacement identity the source returned.
  await expect(page.getByTestId("catalog-groups")).toContainText(renamed)
  await expect(page.getByTestId("catalog-groups")).not.toContainText(created)

  // Moving one relation changes two catalog branches. Both are named by the
  // action result; neither schema is parsed out of an opaque node id here.
  // Where it goes is picked from the schemas this connection has — the server
  // says the field names a grouping and the level says which there are — and
  // the server's own schemas are not among them.
  await showOnlySchema(page, "demo_lab")
  await catalogCheck(page, "audit_events").click()
  await catalogAction(page, "move_relation")
  await page.getByTestId("field-target_schema").click()
  await expect(page.getByRole("option", { name: "pg_catalog", exact: true })).toHaveCount(0)
  await page.getByRole("option", { name: renamed, exact: true }).click()
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, "audit_events")).toHaveCount(0)

  await showOnlySchema(page, renamed)
  await expect(catalogRow(page, "audit_events")).toBeVisible()
  await catalogCheck(page, "audit_events").click()
  await catalogAction(page, "move_relation")
  await page.getByTestId("field-target_schema").click()
  await page.getByRole("option", { name: "demo_lab", exact: true }).click()
  await page.getByTestId("action-submit").click()
  await expect(catalogRow(page, "audit_events")).toHaveCount(0)

  // Empty now, so the source's rolled-back preview says the drop is bounded
  // to the schema itself before the destructive confirmation is accepted.
  await catalogAction(page, "drop_schema")
  await expect(page.getByTestId("action-preview")).toContainText("is empty")
  await page.getByTestId("action-submit").click()
  await expect(page.getByTestId("catalog-groups")).toContainText("public")

  await deleteConnector(page, connector)
  await expect(connectorRow(page, connector)).toHaveCount(0)
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

  // One schema on as the workflow's initial destination; the dialog can then
  // choose another existing schema or ask the database to create one.
  await showOnlySchema(page, "demo_lab")
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
  await expect(page.getByTestId("file-to-relation-dialog")).toContainText("demo_lab")
  await page.getByTestId("load-file").setInputFiles({
    name: "regions.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("code,label\nEU,Europe\nUS,United States\n"),
  })
  await page.getByTestId("field-name").fill(table)

  // Each column of the file stands on its own row against the name it will
  // have, under a legend that says which side is which. Two pairs to a row
  // fitted more on the screen and left the reader guessing which name
  // belonged to which column.
  const columns = page.getByTestId("load-columns")
  await expect(columns).toContainText("In the file")
  await expect(columns).toContainText("Column in the new table")
  await expect(page.getByTestId("load-column-code")).toContainText("code")
  await expect(page.getByTestId("load-tally")).toHaveText("all 2")

  // A column that would be created without a name refuses the whole thing,
  // and the block says so: a compact field keeps no room for a message under
  // it, and the button it refuses is at the other end of the dialog.
  await page.getByTestId("load-column-label").getByRole("textbox").fill("")
  await expect(page.getByTestId("load-tally")).toHaveText("1 of them needs a name")
  await expect(page.getByTestId("load-create")).toBeDisabled()
  await page.getByTestId("load-column-label").getByRole("textbox").fill("label")

  await page.getByTestId("load-create").click()

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
  await showOnlySchema(page, "demo_lab")

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

test("installs an extension from the report that lists them, and removes it", async ({
  page,
}) => {
  const name = `e2e-extension-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await catalogRow(page, "System").click()
  await catalogRow(page, "Extensions").click()

  // Offered over the rows of this report and of no other: the source names
  // what may be done to what it lists, and nothing here is a catalog action
  // over the node itself (D70).
  const install = page.getByTestId("grid-row-command-run-install_extension")
  const remove = page.getByTestId("grid-row-command-run-drop_extension")
  await expect(install).toBeDisabled()
  await expect(remove).toBeDisabled()

  // Filtered rather than read off row 0: the report lists every extension the
  // server offers, so the name alone proves nothing — `installed` does.
  await addFilter(page, "name", "equals", "pg_trgm")
  await expect(page.getByTestId("grid-cell-0-installed")).toHaveText("false")

  await page.getByTestId("grid-select-row-0").click()
  await expect(install).toBeEnabled()
  await install.click()
  await expect(
    toast(page, "1 extension installed")
  ).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-installed")).toHaveText("true")

  // Removing says so first: the command declares itself destructive, and the
  // grid asks before running one that does.
  await page.getByTestId("grid-select-row-0").click()
  await expect(remove).toBeEnabled()
  await remove.click()
  await page.getByTestId("confirm-accept").click()
  await expect(
    toast(page, "1 extension removed")
  ).toBeVisible()
  await expect(page.getByTestId("grid-cell-0-installed")).toHaveText("false")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("makes a database user from the report that lists the roles", async ({
  page,
}) => {
  const name = `e2e-role-${Date.now()}`
  // Named per run, and left behind on purpose: a role is the server's, and
  // nothing in this application removes one. The same choice the scenarios
  // that load a table per run make about the fixture schema.
  const role = `e2e_role_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await catalogRow(page, "System").click()
  await expect(page.getByTestId("catalog-list")).toContainText("Roles")
  await catalogCheck(page, "Roles").click()

  // Offered here and on no other report, and offered at all only because
  // this connection belongs to the person looking at it (D79).
  await catalogAction(page, "create_role")
  const dialog = page.getByTestId("action-dialog")
  await dialog.getByTestId("field-name").fill(role)
  // Masked by the generic form, because the source said `SecretStr` and
  // nothing on this side knows what the field is for.
  const password = dialog.getByTestId("field-password")
  await expect(password).toHaveAttribute("type", "password")
  await password.fill("a-long-enough-password")
  await page.getByTestId("action-submit").click()

  // Filtered rather than read off row 0: the report lists every role the
  // server has, so a row exists whatever happened.
  await catalogRow(page, "Roles").click()
  await addFilter(page, "name", "equals", role)
  await expect(page.getByTestId("grid-cell-0-name")).toHaveText(role)
  await expect(page.getByTestId("grid-cell-0-can_login")).toHaveText("true")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("drops several relations in one request", async ({ page }) => {
  const name = `e2e-drop-many-${Date.now()}`
  // Named per run for the reason the CSV scenario names its table: the fixture
  // schema is rebuilt on `docker compose up` and not between runs.
  const first = `dropped_a_${Date.now()}`
  const second = `dropped_b_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await showOnlySchema(page, "demo_lab")

  await loadCsv(page, first)
  await loadCsv(page, second)

  // Both ticked: what a set admits is what all of it admits, and the source
  // says Drop is one of those.
  await catalogCheck(page, first).click()
  await catalogCheck(page, second).click()
  await catalogAction(page, "drop_relation")

  // One account of the whole selection, because the source is asked about the
  // set rather than about each of them in turn (D68).
  await expect(page.getByTestId("action-preview")).toContainText("2 relations")
  await page.getByTestId("action-submit").click()

  await expect(catalogRow(page, first)).toHaveCount(0)
  await expect(catalogRow(page, second)).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("writes the model of a schema out as code", async ({ page }) => {
  const name = `e2e-model-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  // The schema is the useful subject: a diagram of one table is a rectangle,
  // and a diagram of a schema is the thing people draw (D73). A schema is a
  // grouping rather than a row, so choosing it in the level control is how it
  // becomes what the action acts on.
  await showOnlySchema(page, "demo_lab")
  await catalogAction(page, "describe_model")

  // A window of its own, showing the model before anything is saved. The three
  // dialects are three names on one line, and the words are the source's.
  const dialog = page.getByTestId("model-code-dialog")
  await expect(dialog).toBeVisible()
  await expect(page.getByTestId("model-code-dialect-dbml")).toContainText(
    "dbdiagram.io"
  )
  await expect(dialog).toContainText("Table demo_lab.")

  // The site that draws this dialect is offered beside Copy and Save.
  await expect(page.getByTestId("model-code-site")).toBeVisible()

  // Another dialect is one press, and the document changes under it.
  await page.getByTestId("model-code-dialect-django").click()
  await expect(dialog).toContainText("models.Model")
  await expect(page.getByTestId("model-code-site")).toHaveCount(0)

  await page.getByTestId("model-code-dialect-sqlalchemy").click()
  await expect(dialog).toContainText("declarative_base")

  // And it is saved from what is already on the screen.
  const started = page.waitForEvent("download")
  await page.getByTestId("model-code-save").click()
  const file = await started

  expect(file.suggestedFilename()).toBe("demo_lab.py")
  await page.getByTestId("model-code-close").click()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
