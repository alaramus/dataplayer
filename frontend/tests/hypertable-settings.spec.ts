import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { catalogAction, catalogCheck, showOnlySchema } from "./utils/catalog"
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

async function openSettings(page: Page) {
  await catalogCheck(page, "readings").check()
  await catalogAction(page, "timescale_design_hypertable", "Timescale")
  await expect(page.getByTestId("hypertable-form")).toBeVisible()
}

test.beforeEach(async () => {
  await requireTimescale()
})

test("changes a hypertable as one reviewed plan and reads it back", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-hypertable-${stamp}`
  const schema = `e2e_hypertable_${stamp}`
  await timescaleSql(
    `CREATE SCHEMA ${schema};
     CREATE TABLE ${schema}.readings (observed_at timestamptz NOT NULL, device integer NOT NULL, value double precision);
     SELECT create_hypertable('${schema}.readings', by_range('observed_at', interval '1 day'));
     INSERT INTO ${schema}.readings VALUES (now(), 1, 1.0);`
  )
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await showOnlySchema(page, schema)
    await openSettings(page)

    const plan = page.getByTestId("hypertable-plan")
    // What the source holds is the design the editor opens with, so there is
    // nothing to apply until something is changed.
    await expect(plan).toContainText("already matches these settings")
    await expect(page.getByTestId("hypertable-apply")).toBeDisabled()

    await page.getByTestId("columnstore-enabled").click()
    await choose(page, "retention-mode", "Drop chunks older than")
    await expect(plan).toContainText("Enter the retention age")
    await page.getByTestId("retention-amount").fill("6")

    await expect(plan).toContainText("Turn the columnstore on")
    await expect(plan).toContainText("Add a retention policy: drop chunks older than 6 months")
    await expect(plan).toContainText("after this session ends")
    await page.getByTestId("hypertable-apply").click()
    await expect(toast(page, "Hypertable changed: 2 changes applied")).toBeVisible()

    expect(
      await timescaleSql(
        `SELECT compression_enabled FROM timescaledb_information.hypertables
         WHERE hypertable_schema = '${schema}' AND hypertable_name = 'readings'`
      )
    ).toBe("t")
    expect(
      await timescaleSql(
        `SELECT config ->> 'drop_after' FROM timescaledb_information.jobs
         WHERE hypertable_schema = '${schema}' AND proc_name = 'policy_retention'`
      )
    ).toBe("6 mons")

    await openSettings(page)
    await expect(plan).toContainText("already matches these settings")
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    await timescaleSql(`DROP SCHEMA IF EXISTS ${schema} CASCADE`)
  }
})
