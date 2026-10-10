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

test("picks a day from the calendar and an index from the list", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-picks-${stamp}`
  const schema = `e2e_picks_${stamp}`
  await timescaleSql(
    `CREATE SCHEMA ${schema};
     CREATE TABLE ${schema}.readings (observed_at timestamptz NOT NULL, value integer);
     SELECT create_hypertable('${schema}.readings', by_range('observed_at', interval '1 day'));`
  )
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await showOnlySchema(page, schema)
    await catalogCheck(page, "readings").check()
    await catalogAction(page, "timescale_reorder_chunks", "Timescale")

    const dialog = page.getByRole("dialog", { name: /Reorder chunks by an index/ })
    // The index is the hypertable's, so the form offers the ones it has.
    await expect(dialog).toBeVisible()
    // A box to type in until the answer arrives, a list once it has.
    const index = dialog.getByRole("combobox", { name: "Index" })
    await expect(index).toBeVisible()
    await index.focus()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("option").filter({ hasText: "readings_observed_at_idx" })).toBeVisible()
    await page.getByRole("option").filter({ hasText: "readings_observed_at_idx" }).click()

    await dialog.getByTestId("date-time-picker").first().click()
    await page.getByRole("button", { name: "15", exact: true }).first().click()
    await expect(page.getByTestId("field-ends_by")).toHaveValue(/^\d{4}-\d{2}-15T\d{2}:\d{2}:\d{2}Z$/)
    // The calendar stays open for the time beside it; it and the window cover what clean-up clicks.
    await page.keyboard.press("Escape")
    await dialog.getByRole("button", { name: "Cancel" }).click()
    await expect(dialog).toHaveCount(0)
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    await timescaleSql(`DROP SCHEMA IF EXISTS ${schema} CASCADE`)
  }
})

test("takes values of an integer time column instead of a calendar", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-ticks-${stamp}`
  const schema = `e2e_ticks_${stamp}`
  await timescaleSql(
    `CREATE SCHEMA ${schema};
     CREATE TABLE ${schema}.ticks (tick bigint NOT NULL, value integer);
     SELECT create_hypertable('${schema}.ticks', by_range('tick', 100));
     INSERT INTO ${schema}.ticks SELECT g, g FROM generate_series(0, 599) AS g;`
  )
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await showOnlySchema(page, schema)
    await catalogCheck(page, "ticks").check()
    await catalogAction(page, "timescale_drop_chunks", "Timescale")

    const dialog = page.getByTestId("action-dialog")
    // The source says what the bound is on this hypertable; the calendar goes with the instant.
    await expect(dialog).toContainText('A value of "tick", the bigint column')
    await expect(dialog.getByTestId("date-time-picker")).toHaveCount(0)
    await page.getByTestId("field-ends_by").fill("200")
    const preview = page.getByTestId("action-preview")
    await expect(preview).toContainText("Drop 2 chunks")
    await expect(preview).toContainText("Whole chunks from the earliest chunk to 200")
    await dialog.getByRole("button", { name: "Cancel" }).click()
    await expect(dialog).toHaveCount(0)
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    await timescaleSql(`DROP SCHEMA IF EXISTS ${schema} CASCADE`)
  }
})
