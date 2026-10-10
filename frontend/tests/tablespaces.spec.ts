import { expect, test } from "@playwright/test"

import { addFilter, catalogRow } from "./utils/catalog"
import { login } from "./utils/login"
import { createTimescaleConnector, requireTimescale, timescaleSql } from "./utils/timescale"
import { deleteConnector, openConnector } from "./utils/workspace"

// The TimescaleDB service connects as a superuser, which making a tablespace
// takes; the extension itself plays no part here (D210).
test.beforeEach(async () => {
  await requireTimescale()
})

test("a tablespace is made, renamed and removed from the Tablespaces report", async ({ page }) => {
  const stamp = Date.now()
  const connector = `e2e-spaces-${stamp}`
  const name = `e2e_space_${stamp}`
  const path = `/tmp/${name}`
  // The directory is the server's to have; DataPlayer never makes one.
  await timescaleSql(`COPY (SELECT 1) TO PROGRAM 'mkdir -p ${path}'`)
  try {
    await login(page)
    await createTimescaleConnector(page, connector)
    await openConnector(page, connector)
    await catalogRow(page, "System").click()
    await catalogRow(page, "Tablespaces").click()

    await page.getByTestId("grid-node-action-run-create_tablespace").click()
    const dialog = page.getByTestId("action-dialog")
    await expect(dialog).toContainText("must exist, be empty")
    await page.getByTestId("field-name").fill(name)
    await page.getByTestId("field-location").fill(path)
    await page.getByTestId("action-submit").click()
    await expect(dialog).toHaveCount(0)

    // By its directory, which stays what it was when the name changes.
    await addFilter(page, "location", "equals", path)
    await expect(page.getByTestId("grid-cell-0-name")).toHaveText(name)

    // Renaming is about one row, so it is offered over the row picked.
    await page.getByTestId("grid-select-row-0").click()
    await page.getByTestId("grid-picked-run-rename_tablespace").click()
    // The window's title names the row it was opened over.
    await expect(page.getByRole("dialog", { name: `Rename tablespace — ${name}` })).toBeVisible()
    await page.getByTestId("field-new_name").fill(`${name}_r`)
    await page.getByTestId("action-submit").click()
    await expect(dialog).toHaveCount(0)
    await expect
      .poll(() => timescaleSql(`SELECT count(*) FROM pg_tablespace WHERE spcname = '${name}_r'`))
      .toBe("1")

    await expect(page.getByTestId("grid-cell-0-name")).toHaveText(`${name}_r`)
    await page.getByTestId("grid-row-0").hover()
    await page.getByTestId("grid-row-command-drop_tablespace-0").click()
    await page.getByTestId("confirm-accept").click()
    await expect
      .poll(() => timescaleSql(`SELECT count(*) FROM pg_tablespace WHERE spcname LIKE '${name}%'`))
      .toBe("0")
  } finally {
    await deleteConnector(page, connector).catch(() => undefined)
    for (const left of [name, `${name}_r`]) {
      await timescaleSql(`DROP TABLESPACE IF EXISTS ${left}`).catch(() => undefined)
    }
  }
})
