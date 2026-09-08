import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, editConnector } from "./utils/workspace"

test("connection Options reloads detected features after extension removal", async ({ page }) => {
  const name = `e2e-timescale-features-${Date.now()}`
  let installed = true
  await page.route("**/api/v1/connectors/*/features", async (route) => {
    await route.fulfill({
      json: {
        observed_at: "2026-09-08T12:00:00Z",
        features: [{
          code: "timescaledb", title: "TimescaleDB",
          state: installed ? "available" : "absent",
          installed_version: installed ? "2.18.0" : null,
          reason: null,
        }],
      },
    })
  })
  await login(page)
  await createPostgresConnector(page, name)
  try {
    await editConnector(page, name)
    await page.getByTestId("connector-tab-options").click()
    const feature = page.getByTestId("source-feature-timescaledb")
    await expect(feature).toContainText("2.18.0")
    await expect(feature).toContainText("Available for inspection")
    installed = false
    await page.getByTestId("reload-source-features").click()
    await expect(feature).toContainText("Not installed")
    await expect(feature).not.toContainText("2.18.0")
  } finally {
    await deleteConnector(page, name)
  }
})
