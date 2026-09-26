import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode } from "./utils/catalog"
import { createFileConnector, createRedisConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { REDIS, redisCommands } from "./utils/redis"
import { deleteConnector, openConnector } from "./utils/workspace"

// A folder of Redis hashes declared a table (D170), and a Redis key saved as
// CSV through Paste (D171). The keys are written straight into the scenarios'
// own database of the development Redis, and taken out again at the end.

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
