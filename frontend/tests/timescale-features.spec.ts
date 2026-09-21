import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, editConnector } from "./utils/workspace"

/**
 * What the source says it is, where it is asked: the panel after a check.
 *
 * It used to live in the connection's Options, which is the one place nobody
 * opens to find out what they are connecting to. The check is the question,
 * so the answer is beside it — and pressing the button again is the reload
 * that section used to need a button of its own for.
 */
test("a check says what the server is and what is installed in it", async ({ page }) => {
  const name = `e2e-timescale-features-${Date.now()}`
  let installed = true
  await page.route("**/api/v1/connectors/check-draft", async (route) => {
    await route.fulfill({
      json: {
        ok: true,
        message: "Connection successful",
        latency_ms: 3,
        features: {
          observed_at: "2026-09-08T12:00:00Z",
          server_version: "17.6",
          features: [{
            code: "timescaledb", title: "TimescaleDB",
            state: installed ? "available" : "absent",
            installed_version: installed ? "2.18.0" : null,
            reason: null,
          }],
        },
      },
    })
  })
  await login(page)
  await createPostgresConnector(page, name)
  try {
    await editConnector(page, name)
    await page.getByTestId("check-draft").click()

    // The server first: which TimescaleDB is installed says nothing until it
    // is known which server it is installed in. The name of the source is the
    // label of the line and the version is its value, so the panel is what
    // holds both.
    const facts = page.getByTestId("check-source-facts")
    await expect(facts).toContainText("PostgreSQL")
    await expect(page.getByTestId("source-fact-server")).toContainText("17.6")
    const feature = page.getByTestId("source-fact-timescaledb")
    await expect(feature).toContainText("2.18.0")

    // Checking again is what re-reads it; there is no separate reload.
    installed = false
    await page.getByTestId("check-draft").click()
    await expect(feature).toContainText("Not installed")
    await expect(feature).not.toContainText("2.18.0")
  } finally {
    await deleteConnector(page, name)
  }
})
