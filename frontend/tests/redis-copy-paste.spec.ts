import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, catalogRow, openNode } from "./utils/catalog"
import {
  createFileConnector,
  createRedisConnector,
} from "./utils/connectors"
import { login } from "./utils/login"
import { REDIS, redisCommands } from "./utils/redis"
import { requireE2EService } from "./utils/services"
import { deleteConnector, openConnector } from "./utils/workspace"

// A Redis key copied to file storage as CSV through Paste (D171). Keys live in
// the scenarios' own database of the development Redis and are removed again.

test.beforeEach(async () => {
  await requireE2EService("redis")
})

test("copies a Redis key into file storage as CSV through Paste", async ({ page }) => {
  const stamp = Date.now()
  const redis = `e2e-redis-${stamp}`
  const files = `e2e-redis-files-${stamp}`
  const session = `s${stamp}:`
  const saved = `s${stamp}-token.csv`
  const database = String(REDIS.database)
  const key = `${session}token`
  await redisCommands([["SET", key, "abc"]])
  try {
    await login(page)
    await createRedisConnector(page, redis)
    await createFileConnector(page, files)
    await openConnector(page, redis)

    // A copied key keeps its Redis value in a CSV named after it, with the
    // colon replaced by a safe filename character.
    await page.getByTestId(`keyspace-row-f${database}:${session}`).click()
    await page.getByTestId(`keyspace-row-k${database}:${key}`).click()
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
    await redisCommands([["DEL", key]])
  }
})
