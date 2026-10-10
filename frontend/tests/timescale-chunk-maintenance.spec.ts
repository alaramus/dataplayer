import { expect, test } from "@playwright/test"

import { catalogAction, catalogCheck, showOnlySchema } from "./utils/catalog"
import { login } from "./utils/login"
import { createTimescaleConnector, requireTimescale, timescaleSql } from "./utils/timescale"
import { deleteConnector, openConnector } from "./utils/workspace"

test.beforeEach(async () => {
  await requireTimescale()
})

test("drops exactly the reviewed chunks as a job from the Timescale submenu", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-chunks-${stamp}`
  const schema = `e2e_chunks_${stamp}`
  await timescaleSql(
    `CREATE SCHEMA ${schema};
     CREATE TABLE ${schema}.readings (observed_at timestamptz NOT NULL, value integer);
     SELECT create_hypertable('${schema}.readings', by_range('observed_at', interval '1 day'));
     INSERT INTO ${schema}.readings
       SELECT TIMESTAMPTZ '2020-01-01 00:00+00' + make_interval(hours => g), g FROM generate_series(0, 95) AS g;`
  )
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await showOnlySchema(page, schema)
    await catalogCheck(page, "readings").check()
    await catalogAction(page, "timescale_drop_chunks", "Timescale")

    const dialog = page.getByTestId("action-dialog")
    await expect(dialog).toContainText("every row in them")
    await page.getByTestId("field-ends_by").fill("2020-01-03T00:00:00Z")
    const preview = page.getByTestId("action-preview")
    await expect(preview).toContainText("Drop 2 chunks")
    await expect(preview).toContainText("never by an age read when the job runs")
    await page.getByTestId("action-submit").click()
    await expect(dialog).toHaveCount(0)

    // The job runs on the server, one chunk per unit; what is left is the later two days.
    await expect
      .poll(
        () =>
          timescaleSql(
            `SELECT count(*) FROM timescaledb_information.chunks
             WHERE hypertable_schema = '${schema}' AND hypertable_name = 'readings'`
          ),
        { timeout: 30_000 }
      )
      .toBe("2")
    expect(await timescaleSql(`SELECT count(*) FROM ${schema}.readings`)).toBe("48")
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    await timescaleSql(`DROP SCHEMA IF EXISTS ${schema} CASCADE`)
  }
})
