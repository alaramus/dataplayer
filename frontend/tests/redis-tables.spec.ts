import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode, pickSchema } from "./utils/catalog"
import {
  createFileConnector,
  createPostgresConnector,
  createRedisConnector,
} from "./utils/connectors"
import { login } from "./utils/login"
import { REDIS, redisCommands } from "./utils/redis"
import { requireE2EService } from "./utils/services"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

// A folder of Redis hashes declared a table (D170), and a Redis key saved as
// CSV through Paste (D171). The keys are written straight into the scenarios'
// own database of the development Redis, and taken out again at the end.

test.beforeEach(async () => {
  await requireE2EService("redis")
})

/** The text of a cell without the controls that live in it. */
function cellValue(page: Page, testId: string) {
  return page.getByTestId(testId).locator("> span").first()
}

async function choose(page: Page, testId: string, option: string) {
  await page.getByTestId(testId).click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test("references a Redis table by its key from a relation, and follows it both ways", async ({
  page,
}) => {
  const stamp = Date.now()
  const database = `e2e-redis-ref-db-${stamp}`
  const redis = `e2e-redis-ref-${stamp}`
  const orgs = `o${stamp}:`
  let keys: string[] = []
  try {
    await login(page)
    await createPostgresConnector(page, database)
    await createRedisConnector(page, redis)

    // The value the first organization holds, which the Redis table is given
    // a hash for.
    await openConnector(page, database)
    await pickSchema(page, "demo_lab")
    await openNode(page, "organizations")
    await expect(page.getByTestId("grid-cell-0-organization_id")).toBeVisible()
    const owner = (await cellValue(page, "grid-cell-0-organization_id").innerText()).trim()
    keys = [`${orgs}${owner}`, `${orgs}elsewhere`]
    await redisCommands([
      ["HSET", `${orgs}${owner}`, "name", "Kept in Redis"],
      ["HSET", `${orgs}elsewhere`, "name", "Another"],
    ])

    await openConnector(page, redis)
    await page.getByTestId(`keyspace-row-f${String(REDIS.database)}:${orgs}`).click()
    await catalogAction(page, "client:describe-table")
    await page.getByTestId("declare-table-name").fill("orgs")
    await page.getByTestId("declare-table-save").click()
    await expect(page.getByTestId("declare-table")).toHaveCount(0)

    // Drawn from the relation's structure: of the Redis table, `key` alone
    // can be looked up, so it is the one column offered (D172).
    await rowsTabs(page).first().click()
    await page.getByTestId("grid-structure").click()
    const view = page.getByTestId("structure-view")
    await view.getByTestId("structure-declare-reference").click()
    const dialog = page.getByTestId("declare-reference-dialog")
    await choose(page, "declare-reference-near-column", "organization_id")
    await choose(page, "declare-reference-source", redis)
    await page.getByTestId(`declare-reference-node-db${String(REDIS.database)}`).click()
    await page.getByTestId("declare-reference-node-orgs").click()
    await page.getByTestId("declare-reference-far-column").click()
    await expect(page.getByRole("option")).toHaveText(["key"])
    await page.getByRole("option", { name: "key", exact: true }).click()
    await page.getByTestId("declare-reference-run").click()
    await expect(dialog).toBeHidden()
    await expect(view.getByTestId("declared-reference")).toContainText(
      `organization_id → ${redis} · orgs.key`
    )

    // Followed from the relation: the Redis table, filtered to the one key.
    await rowsTabs(page).first().click()
    await page.getByTestId("grid-cell-0-organization_id").hover()
    await page.locator('[data-testid^="grid-follow-0-declared:"]').click()
    await page.locator('[data-testid^="menu-item-declared:"]').click()
    await expect(rowsTabs(page)).toHaveCount(2)
    await expect(rowsTabs(page).last()).toContainText("orgs")
    await expect(page.getByTestId("grid-page-range")).toHaveText("Rows 1–1")
    await expect(cellValue(page, "grid-cell-0-key")).toHaveText(owner)
    await expect(cellValue(page, "grid-cell-0-name")).toHaveText("Kept in Redis")
    await page.screenshot({ path: "test-results/redis-reference-followed.png" })

    // And back, from the key.
    await page.getByTestId("grid-cell-0-key").hover()
    await page.locator('[data-testid^="grid-follow-0-declared:"]').click()
    await page.locator('[data-testid^="menu-item-declared:"]').click()
    // The relation's tab is already open, so it is the one that shows them.
    await expect(
      page.locator('[data-testid^="workspace-tab-rows:"][aria-label="organizations"]')
    ).toHaveAttribute("aria-selected", "true")
    await expect(cellValue(page, "grid-cell-0-organization_id")).toHaveText(owner)

    await deleteConnector(page, redis)
    await deleteConnector(page, database)
  } finally {
    if (keys.length > 0) await redisCommands([["DEL", ...keys]])
  }
})

test("adds a row to a Redis table, edits a cell and deletes the row", async ({ page }) => {
  const stamp = Date.now()
  const redis = `e2e-redis-edit-${stamp}`
  const folder = `e${stamp}:`
  const database = String(REDIS.database)
  await redisCommands([["HSET", `${folder}1`, "name", "Ada", "age", "36"]])
  try {
    await login(page)
    await createRedisConnector(page, redis)
    await openConnector(page, redis)
    await page.getByTestId(`keyspace-row-f${database}:${folder}`).click()
    await catalogAction(page, "client:describe-table")
    await page.getByTestId("declare-table-name").fill("people")
    await page.getByTestId("declare-table-save").click()
    await page.getByTestId(`keyspace-row-t${database}:${folder}`).click()
    await expect(page.getByTestId("grid-cell-0-name")).toHaveText("Ada")

    // A new row is a new hash, named by its key (D173).
    await page.getByTestId("grid-insert").click()
    await page.getByTestId("grid-insert-value-key").fill("2")
    await page.getByTestId("grid-insert-value-name").fill("Grace")
    await page.getByTestId("grid-insert-save").click()
    await expect(page.getByTestId("grid-cell-1-key")).toHaveText("2")
    await expect(page.getByTestId("grid-cell-1-name")).toHaveText("Grace")

    // A cell is one field of one hash.
    await page.getByTestId("grid-cell-0-age").dblclick()
    await page.getByTestId("grid-edit-value").fill("37")
    await page.getByTestId("grid-edit-save").click()
    await expect(page.getByTestId("grid-cell-0-age")).toHaveText("37")

    // Deleting the row deletes its key.
    await page.getByTestId("grid-select-row-1").click()
    await page.getByTestId("grid-delete").click()
    await page.getByTestId("confirm-accept").click()
    await expect(page.getByTestId("grid-cell-1-key")).toHaveCount(0)
    await page.screenshot({ path: "test-results/redis-table-edited.png" })

    await deleteConnector(page, redis)
  } finally {
    await redisCommands([["DEL", `${folder}1`, `${folder}2`]])
  }
})

test("declares a table over a folder of hashes and saves a key as CSV", async ({ page }) => {
  const stamp = Date.now()
  const redis = `e2e-redis-${stamp}`
  const files = `e2e-redis-files-${stamp}`
  const users = `u${stamp}:`
  const session = `s${stamp}:`
  const saved = `s${stamp}-token.csv`
  const database = String(REDIS.database)
  const keys = [`${users}1`, `${users}2`, `${users}count`, `${session}token`]
  await redisCommands([
    ["HSET", `${users}1`, "name", "Ada", "email", "ada@example.com"],
    ["HSET", `${users}2`, "name", "Grace"],
    ["SET", `${users}count`, "2"],
    ["SET", `${session}token`, "abc"],
  ])
  try {
    await login(page)
    await createRedisConnector(page, redis)
    await createFileConnector(page, files)
    await openConnector(page, redis)

    // The folder picked in the tree is what the line is about; its window
    // proposes the fields of the hashes in it.
    await page.getByTestId(`keyspace-row-f${database}:${users}`).click()
    await catalogAction(page, "client:describe-table")
    const window = page.getByTestId("declare-table")
    await expect(page.getByTestId("declare-table-field-name")).toBeVisible()
    await expect(page.getByTestId("declare-table-field-email")).toBeVisible()
    await page.getByTestId("declare-table-name").fill("users")
    await page.screenshot({ path: "test-results/redis-table-declare.png" })
    await page.getByTestId("declare-table-save").click()
    await expect(window).toHaveCount(0)

    // It stands beside its folder and opens as rows, `key` first; the string
    // in the folder is not a row, and the grid says so.
    const table = page.getByTestId(`keyspace-row-t${database}:${users}`)
    await expect(table).toContainText("users")
    await expect(page.getByTestId(`keyspace-row-f${database}:${users}`)).toBeVisible()
    await table.click()
    const grid = page.getByTestId("row-grid")
    await expect(grid).toContainText("ada@example.com")
    await expect(grid).toContainText("Grace")
    await expect(page.getByTestId("grid-notice")).toContainText("1 key of another type is not a row")
    await page.screenshot({ path: "test-results/redis-table-grid.png" })

    // A key copied and pasted into a folder is a CSV named after it, a colon
    // being no file name everywhere.
    await page.getByTestId(`keyspace-row-f${database}:${session}`).click()
    await page.getByTestId(`keyspace-row-k${database}:${session}token`).click()
    await catalogAction(page, "client:copy")
    await openConnector(page, files)
    await openNode(page, "reports")
    await catalogAction(page, "client:cross-paste")
    await expect(page.getByTestId("cross-paste-file-name")).toHaveValue(saved)
    await page.getByTestId("cross-paste-save").click()
    await expect(catalogRow(page, saved)).toBeVisible()

    const box = catalogCheck(page, saved)
    if (!(await box.isChecked())) await box.click()
    await catalogAction(page, "delete")
    await page.getByTestId("action-submit").click()
    await expect(catalogRow(page, saved)).toHaveCount(0)
    await deleteConnector(page, files)
    await deleteConnector(page, redis)
  } finally {
    await redisCommands([["DEL", ...keys]])
  }
})
