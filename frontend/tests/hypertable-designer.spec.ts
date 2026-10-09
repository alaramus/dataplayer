import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { catalogAction, showOnlySchema } from "./utils/catalog"
import { login } from "./utils/login"
import { toast } from "./utils/notices"
import { createTimescaleConnector, requireTimescale, timescaleSql } from "./utils/timescale"
import { deleteConnector, openConnector } from "./utils/workspace"

/** Choose one option of a kit select that is already on screen. */
async function choose(page: Page, field: string, option: string) {
  await page
    .getByTestId(field)
    .locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' q-field ')][1]")
    .click()
  await page.getByRole("option", { name: option, exact: true }).click()
}

test.beforeEach(async () => {
  await requireTimescale()
})

test("creates a table as a hypertable from the designer, its time index in plain sight", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-designed-hypertable-${stamp}`
  const schema = `e2e_designed_${stamp}`
  const table = `readings_${stamp}`
  await timescaleSql(`CREATE SCHEMA ${schema}`)
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await showOnlySchema(page, schema)
    await catalogAction(page, "create_table")
    await expect(page.getByTestId("table-designer")).toBeVisible()

    await page.getByTestId("table-name").fill(table)
    await page.getByTestId("column-name").fill("device")
    await choose(page, "column-type", "Integer")

    // A second column, so the time index is not the primary key's.
    await page.getByTestId("add-columns").click()
    await page.getByTestId("column-name").fill("observed_at")
    await choose(page, "column-type", "Timestamp with time zone")
    await page.getByTestId("column-not-null").click()

    await page.getByTestId("object-hypertable").click()
    await page.getByTestId("table-hypertable").click()
    // The index create_hypertable would have added is one of the draft's own.
    await expect(page.getByTestId("section-indexes")).toContainText("1")
    // The primary key is on the first column alone, which a hypertable refuses.
    await expect(page.getByTestId("design-problems")).toContainText(
      "The primary key of a hypertable must hold its time column"
    )
    await page.getByTestId("section-constraints").click()
    await page.getByTestId("constraints-inspector").getByRole("checkbox", { name: "observed_at" }).click()
    await expect(page.getByTestId("design-problems")).toHaveCount(0)
    const sql = page.getByTestId("design-sql")
    await page.getByTestId("object-hypertable").click()
    await expect(sql).toContainText("create_hypertable")
    await expect(sql).toContainText("false, false, false")

    await page.getByTestId("hypertable-retention").click()
    await expect(page.getByTestId("design-review-sql")).toBeDisabled()
    await page.getByTestId("hypertable-retention-amount").fill("360")
    await expect(page.getByTestId("design-review-sql")).toBeEnabled()

    await page.getByTestId("design-review-sql").click()
    await expect(page.getByTestId("design-review")).toContainText("add_retention_policy")
    await page.getByTestId("design-create").click()
    await expect(toast(page, table)).toBeVisible()

    expect(
      await timescaleSql(
        `SELECT count(*) FROM timescaledb_information.hypertables
         WHERE hypertable_schema = '${schema}' AND hypertable_name = '${table}'`
      )
    ).toBe("1")
    expect(
      await timescaleSql(
        `SELECT count(*) FROM timescaledb_information.jobs
         WHERE hypertable_schema = '${schema}' AND proc_name = 'policy_retention'`
      )
    ).toBe("1")
    // The primary key's index and the time index; TimescaleDB added none of its own.
    expect(
      await timescaleSql(`SELECT count(*) FROM pg_indexes WHERE schemaname = '${schema}' AND tablename = '${table}'`)
    ).toBe("2")
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    await timescaleSql(`DROP SCHEMA IF EXISTS ${schema} CASCADE`)
  }
})
