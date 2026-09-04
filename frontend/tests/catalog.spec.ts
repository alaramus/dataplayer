import { expect, test } from "@playwright/test"

import type { Page } from "@playwright/test"

import { addFilter, catalogRow, hideSchema, pickSchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import {
  catalogTabIcon,
  connectorRow,
  connectionsTab,
  deleteConnector,
  openConnector,
} from "./utils/workspace"

test("browses a database as a list filtered by schema", async ({ page }) => {
  const name = `e2e-catalog-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await openConnector(page, name)

  // Schemas are a grouping, not a level: the list shows the relations of the
  // first real schema straight away, without a step through `public`.
  const list = page.getByTestId("catalog-list")
  await expect(list).toContainText("connector")
  await expect(page.getByTestId("catalog-groups")).toContainText("public")

  // A database is one level deep — schemas are a grouping, not a place — so
  // there is no path, and a pill holding nothing but a home button would be
  // one more thing to read on a line that has none to spare.
  await expect(page.getByTestId("catalog-path")).toHaveCount(0)

  // A column is not a row of the catalog: the grid on the right has them.
  await expect(catalogRow(page, "adapter_type")).toHaveCount(0)

  await pickSchema(page, "pg_catalog")
  await expect(list).toContainText("pg_class")
  // Two groupings are on, so each row says which one it came from.
  await expect(catalogRow(page, "pg_class")).toContainText("pg_catalog")

  await page.getByTestId("catalog-filter").fill("pg_class")
  await expect(catalogRow(page, "connector")).toHaveCount(0)
  await expect(catalogRow(page, "pg_class")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("detects a framework and toggles its table filter from the catalog", async ({ page }) => {
  const name = `e2e-framework-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  const badge = page.getByTestId("catalog-framework-alembic")
  const filter = page.getByTestId("catalog-filter")
  await expect(badge).toBeVisible()
  await expect(badge).toHaveAttribute("aria-pressed", "false")
  await badge.click()
  await expect(filter).toHaveValue("alembic_version")
  await expect(badge).toHaveAttribute("aria-pressed", "true")
  await expect(catalogRow(page, "alembic_version")).toBeVisible()
  await expect(catalogRow(page, "connector")).toHaveCount(0)

  // The detector remains visible while its filter narrows the table list.
  await badge.click()
  await expect(filter).toHaveValue("")
  await expect(catalogRow(page, "connector")).toBeVisible()
  await filter.fill("connector")
  await filter.press("Escape")
  await expect(badge).toHaveAttribute("aria-pressed", "false")
  await badge.focus()
  await badge.press("Enter")
  await expect(filter).toHaveValue("alembic_version")
  await badge.click()

  // A marker in an unselected schema must not label the remaining schemas.
  await hideSchema(page, "public")
  await expect(badge).toHaveCount(0)
  await pickSchema(page, "public")
  await expect(badge).toBeVisible()
  await deleteConnector(page, name)
})

test("keeps filter history per connector and remembers deletions after reload", async ({ page }) => {
  const first = `e2e-history-first-${Date.now()}`
  const second = `e2e-history-second-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, first)
  await createPostgresConnector(page, second)
  await openConnector(page, first)

  const filter = page.getByTestId("catalog-filter")
  const history = page.getByTestId("catalog-search-history")
  await filter.fill("pg_class")
  await filter.press("Enter")
  await filter.fill("connector")
  // Leaving the field remembers ordinary filtering too, without Enter.
  await connectionsTab(page).click()
  await filter.click()
  await expect(history).toBeVisible()
  await expect(filter).toBeFocused()
  // Clicking an already focused field keeps its history open and typing stays possible.
  await filter.click()
  await filter.fill("still typing")
  await expect(filter).toBeFocused()
  await expect(history).toBeVisible()
  await filter.fill("connector")
  await expect(page.getByTestId("menu-item-connector")).toBeVisible()
  await page.getByTestId("menu-item-pg_class").click()
  await expect(filter).toHaveValue("pg_class")
  await expect(filter).toBeFocused()
  await expect(history).toHaveCount(0)

  await filter.click()
  await page.getByRole("button", { name: "Remove “pg_class” from history", exact: true }).click()
  await expect(page.getByTestId("menu-item-pg_class")).toHaveCount(0)
  await expect(page.getByTestId("menu-item-connector")).toBeVisible()
  await expect(filter).toHaveValue("pg_class")
  await page.keyboard.press("Escape")
  await expect(history).toHaveCount(0)
  await filter.click()
  await expect(history).toBeVisible()
  await connectionsTab(page).click()
  await expect(history).toHaveCount(0)

  await openConnector(page, second)
  await filter.click()
  await expect(history).toHaveCount(0)
  await filter.fill("other connector")
  await filter.press("Enter")

  await page.reload()
  await openConnector(page, first)
  await filter.click()
  await expect(page.getByTestId("menu-item-connector")).toBeVisible()
  await expect(page.getByTestId("menu-item-pg_class")).toHaveCount(0)
  await expect(page.getByTestId("menu-item-other connector")).toHaveCount(0)
  await page.getByRole("button", { name: "Remove “connector” from history", exact: true })
    .press("Enter")
  await expect(page.getByTestId("menu-item-connector")).toHaveCount(0)
  await expect(history).toHaveCount(0)

  for (const name of [first, second]) await deleteConnector(page, name)
})

test("the tab icon of the catalog opens the window of its connection", async ({ page }) => {
  const name = `e2e-head-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  // The icon of the tab, rather than a button in the head: the tab is
  // always visible while the catalog's own column can be collapsed.
  await catalogTabIcon(page).click()
  await expect(page.getByTestId("connector-name")).toHaveValue(name)

  await page.getByTestId("delete-connector").click()
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})

/**
 * The head of a catalog is the same height whatever the source is.
 *
 * Moving between two connections must not move the list under them, and the
 * head holds different things for different sources: a path for a directory,
 * a choice of schemas for a database, and a menu only where the source has
 * actions. Asserted rather than looked at once, because the next source type
 * is what would break it.
 */
async function headHeight(page: Page): Promise<number> {
  const box = await page.locator(".catalog-panel__head").boundingBox()
  if (box === null) throw new Error("the head of the catalog has no box")
  return Math.round(box.height)
}

test("the head of a catalog is one height across source types", async ({ page }) => {
  const database = `e2e-sym-db-${Date.now()}`
  const files = `e2e-sym-files-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  // A database: a choice of schemas and no menu — postgres declares no
  // actions. The icon of the source lives on the tab, not in the head.
  await openConnector(page, database)
  await expect(page.getByTestId("catalog-list")).toContainText("connector")
  const withGroups = await headHeight(page)

  await pickSchema(page, "pg_catalog")
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")
  expect(await headHeight(page)).toBe(withGroups)

  // Personal storage at its root: a menu and a path with only the
  // home button — the strip stays visible even at the top so it does
  // not appear and disappear when walking in and out.
  await openConnector(page, files)
  await expect(page.getByTestId("catalog-path")).toBeVisible()
  await expect(page.getByTestId("catalog-actions")).toBeVisible()
  expect(await headHeight(page)).toBe(withGroups)

  // And inside a folder, where the path appears and the head must not grow.
  await catalogRow(page, "reports").click()
  await expect(page.getByTestId("catalog-path")).toBeVisible()
  expect(await headHeight(page)).toBe(withGroups)

  for (const name of [database, files]) {
    await deleteConnector(page, name)
    await expect(connectorRow(page, name)).toHaveCount(0)
  }
})

test("opens a report the connection publishes about itself", async ({ page }) => {
  const name = `e2e-reports-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  // The section sits at the root beside the schemas and is walked into, so
  // eight rows about the server never sit above the reader's own tables.
  await catalogRow(page, "System").click()
  await expect(page.getByTestId("catalog-list")).toContainText("Tablespaces")
  // The source's own line about each report, not a caption the list invents.
  await expect(catalogRow(page, "Tablespaces")).toContainText("size")

  // A report opens in the ordinary grid, and carries the columns no relation
  // holds: this is the whole reason a report is a statement (D55).
  await catalogRow(page, "Tablespaces").click()
  await expect(page.getByTestId("grid-cell-0-name")).toContainText("pg_default")
  await expect(page.getByTestId("grid-cell-0-objects")).toBeVisible()

  // Read-only: nothing about a subquery names a row to write back to.
  await expect(page.getByTestId("grid-insert-row")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("opens a relation's source-issued DDL without making it editable", async ({ page }) => {
  const name = `e2e-ddl-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await catalogRow(page, "connector").click()
  await expect(page.getByTestId("grid-content")).toBeVisible()
  await page.getByTestId("grid-content").click()

  const ddl = page.getByTestId("sql-editor")
  await expect(ddl).toBeVisible()
  await expect(ddl).toContainText("CREATE TABLE")
  await expect(ddl).toContainText("connector")
  await expect(ddl.locator(".cm-content")).toHaveAttribute("contenteditable", "false")

  await page.getByTestId("sql-view-table").click()
  await expect(page.getByTestId("grid-header")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("the processes report is a task manager, not just a table", async ({ page }) => {
  const name = `e2e-processes-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await catalogRow(page, "System").click()
  await catalogRow(page, "Processes").click()

  // Nobody chose this: the source said the report is about what is happening
  // this second, and the grid started there (D70).
  const refresh = page.getByTestId("grid-auto-refresh")
  await expect(refresh).toHaveAttribute("data-refresh", "5")

  // Nothing but the controls for looking and the commands for acting: a
  // report is a picture of the server, not data to take away (D72).
  for (const gone of [
    "grid-download",
    "grid-share",
    "grid-charts",
    "grid-create-table",
    "grid-query",
  ]) {
    await expect(page.getByTestId(gone)).toHaveCount(0)
  }
  await expect(page.getByTestId("grid-filter")).toBeVisible()

  // The commands are the source's own, offered on this report and on no
  // other, and dead until there is something to act on.
  const cancel = page.getByTestId("grid-row-command-run-cancel_query")
  const terminate = page.getByTestId("grid-row-command-run-terminate_backend")
  await expect(cancel).toBeDisabled()
  await expect(terminate).toBeDisabled()

  // An idle client backend: cancelling one has nothing to cancel, which is
  // what makes this safe to run against the database the suite is using.
  await addFilter(page, "state", "equals", "idle")
  await page.getByTestId("grid-select-row-0").click()
  await expect(cancel).toBeEnabled()

  await cancel.click()
  await page.getByTestId("confirm-accept").click()
  await expect(
    page.locator(".q-notification", { hasText: "asked to stop" })
  ).toBeVisible()

  // Another report in the same section offers none of it: the commands
  // belong to one node, not to the source.
  await catalogRow(page, "Settings").click()
  await expect(page.getByTestId("grid-cell-0-name")).toBeVisible()
  await expect(page.getByTestId("grid-row-command-run-cancel_query")).toHaveCount(0)
  await expect(page.getByTestId("grid-auto-refresh")).toHaveAttribute(
    "data-refresh",
    "off"
  )
  // Settings is a report too, so it withdraws the same five.
  await expect(page.getByTestId("grid-charts")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
