import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector, DATABASE, pickAdapterType } from "./utils/connectors"
import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, editConnector, openConnector } from "./utils/workspace"

/**
 * What this sub-project is for: two connections on screen at once, one read
 * while the other is filled in. None of it can be shown by a unit test —
 * whether two rectangles are both visible is a question about a browser.
 */

function windows(page: Page): Locator {
  return page.locator('[data-testid^="window-connector"]').filter({ has: page.locator("footer") })
}

test("keeps two connection windows open side by side", async ({ page }) => {
  const existing = `e2e-win-a-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, existing)

  // One window on a stored connection, to read values out of.
  await editConnector(page, existing)
  await expect(page.getByTestId("connector-name")).toHaveValue(existing)

  // A second, for a connection being created — the whole point being that
  // the first did not have to be closed to get here.
  await page.getByTestId("add-connector").click()
  await page.getByTestId("adapter-postgres").click()
  await page.getByTestId("create-from-catalog").click()

  await expect(windows(page)).toHaveCount(2)

  const first = await windows(page).nth(0).boundingBox()
  const second = await windows(page).nth(1).boundingBox()
  expect(first).not.toBeNull()
  expect(second).not.toBeNull()
  // Cascaded, not stacked: a window exactly on top of the other would defeat
  // the purpose of having two.
  expect(second?.x).not.toBe(first?.x)

  await deleteConnector(page, existing)
})

test("brings the window already open forward instead of opening a second", async ({
  page,
}) => {
  const name = `e2e-win-one-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await editConnector(page, name)
  await editConnector(page, name)

  // Two windows of one connection are two unsaved edits of one row.
  await expect(windows(page)).toHaveCount(1)

  await deleteConnector(page, name)
})

test("a window can be dragged, and cannot be dragged out of reach", async ({ page }) => {
  const name = `e2e-win-drag-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await editConnector(page, name)

  const frame = windows(page).first()
  const bar = page.locator('[data-testid^="window-bar-connector"]').first()
  const before = await frame.boundingBox()
  const grip = await bar.boundingBox()
  // From where the cursor actually is, not from where the window is: the two
  // differ by half the width of the bar.
  const from = { x: (grip?.x ?? 0) + 20, y: (grip?.y ?? 0) + (grip?.height ?? 0) / 2 }

  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x + 120, from.y + 60, { steps: 8 })
  await page.mouse.up()

  const moved = await frame.boundingBox()
  expect(moved?.x).toBeCloseTo((before?.x ?? 0) + 120, -1)
  expect(moved?.y).toBeCloseTo((before?.y ?? 0) + 60, -1)

  // Thrown at the far corner it must still be grabbable: the old engine
  // clamped nothing, and a window past the edge could not be brought back.
  const grip2 = await bar.boundingBox()
  await page.mouse.move((grip2?.x ?? 0) + 20, (grip2?.y ?? 0) + (grip2?.height ?? 0) / 2)
  await page.mouse.down()
  await page.mouse.move(5000, 5000, { steps: 4 })
  await page.mouse.up()

  const viewport = page.viewportSize()
  const parked = await frame.boundingBox()
  expect(parked?.x).toBeLessThan(viewport?.width ?? 0)
  expect(parked?.y).toBeLessThan(viewport?.height ?? 0)

  // And the strip that stayed is enough to bring it back, which is the whole
  // reason the clamp exists. Back near the top, so the window fits the
  // viewport again: a window may hang past the bottom edge — that is ordinary
  // — and its buttons are out of reach until it is moved, as on any desktop.
  const grip3 = await bar.boundingBox()
  await page.mouse.move((grip3?.x ?? 0) + 20, (grip3?.y ?? 0) + (grip3?.height ?? 0) / 2)
  await page.mouse.down()
  await page.mouse.move(200, 24, { steps: 8 })
  await page.mouse.up()

  const back = await frame.boundingBox()
  expect((back?.y ?? 0) + (back?.height ?? 0)).toBeLessThanOrEqual(viewport?.height ?? 0)

  // Every floating window has the same resize affordance. Shrinking from the
  // corner changes both dimensions and the engine keeps the result.
  const corner = page.locator('[data-testid^="window-resize-bottom-right-connector"]').first()
  const cornerBox = await corner.boundingBox()
  await page.mouse.move(
    (cornerBox?.x ?? 0) + (cornerBox?.width ?? 0) / 2,
    (cornerBox?.y ?? 0) + (cornerBox?.height ?? 0) / 2
  )
  await page.mouse.down()
  await page.mouse.move((cornerBox?.x ?? 0) - 80, (cornerBox?.y ?? 0) - 80, { steps: 4 })
  await page.mouse.up()

  const resized = await frame.boundingBox()
  expect(resized?.width).toBeLessThan(back?.width ?? 0)
  expect(resized?.height).toBeLessThan(back?.height ?? 0)

  await page.getByTestId("cancel-connector").click()
  await expect(windows(page)).toHaveCount(0)
  await deleteConnector(page, name)
})

/** What is actually painted at a point, and whether it belongs to the window. */
async function hitsTheWindow(page: Page, point: { x: number; y: number }): Promise<boolean> {
  return await page.evaluate(
    (at) => document.elementFromPoint(at.x, at.y)?.closest(".app-window") !== null,
    point
  )
}

test("a window is painted over the chrome and over a grid it covers", async ({ page }) => {
  const name = `e2e-win-layer-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  // A grid behind it, because half of what this is about is the sticky header
  // of a table: it is declared with a z-index, and the window was not.
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("row-grid")).toContainText("relname")

  await editConnector(page, name)
  const frame = windows(page).first()
  const bar = page.locator('[data-testid^="window-bar-connector"]').first()

  const grip = await bar.boundingBox()
  await page.mouse.move((grip?.x ?? 0) + 20, (grip?.y ?? 0) + (grip?.height ?? 0) / 2)
  await page.mouse.down()
  // Hard against the top, where the blue header is.
  await page.mouse.move(500, 2, { steps: 8 })
  await page.mouse.up()

  // Not "is the box inside the viewport" — it always was, `clamp` saw to
  // that. The bar was painted over by the header, and a strip that cannot be
  // clicked is a window that cannot be brought back.
  const parked = await bar.boundingBox()
  expect(
    await hitsTheWindow(page, {
      x: (parked?.x ?? 0) + 20,
      y: (parked?.y ?? 0) + (parked?.height ?? 0) / 2,
    })
  ).toBe(true)

  // And the body of the window covers the column headings of the grid rather
  // than the other way round. A point inside both boxes, so the question is
  // only which of the two is painted there.
  const cell = await page.getByTestId("grid-column-relname").boundingBox()
  const box = await frame.boundingBox()
  if (cell === null || box === null) throw new Error("the heading or the window has no box")
  const overlapFrom = Math.max(cell.x, box.x)
  const overlapTo = Math.min(cell.x + cell.width, box.x + box.width)
  expect(overlapTo).toBeGreaterThan(overlapFrom)
  expect(cell.y).toBeGreaterThan(box.y)
  expect(cell.y).toBeLessThan(box.y + box.height)

  expect(
    await hitsTheWindow(page, {
      x: (overlapFrom + overlapTo) / 2,
      y: cell.y + cell.height / 2,
    })
  ).toBe(true)

  await page.getByTestId("cancel-connector").click()
  await deleteConnector(page, name)
})

test("Apply saves and stays, and does not create a second connection", async ({ page }) => {
  const name = `e2e-win-apply-${Date.now()}`
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(name)
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)

  await page.getByTestId("apply-connector").click()
  await expect(connectorRow(page, name)).toBeVisible()
  // Still open — that is what Apply is for.
  await expect(windows(page)).toHaveCount(1)

  // The window is now that connection's window, so a second Apply updates it
  // rather than creating a duplicate.
  await page.getByTestId("apply-connector").click()
  await expect(page.getByTestId(`connector-${name}`)).toHaveCount(1)

  await page.getByTestId("cancel-connector").click()
  await expect(windows(page)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("shows the connection string, and hides it for a source that has none", async ({
  page,
}) => {
  const postgres = `e2e-win-url-${Date.now()}`
  const files = `e2e-win-files-${Date.now()}`
  await login(page)

  await pickAdapterType(page, "postgres")
  await page.getByTestId("connector-name").fill(postgres)
  await page.getByTestId("field-host").fill(DATABASE.host)
  await page.getByTestId("field-port").fill(DATABASE.port)
  await page.getByTestId("field-database").fill(DATABASE.database)
  await page.getByTestId("field-user").fill(DATABASE.user)
  await page.getByTestId("field-password").fill(DATABASE.password)

  // Composed by the server from the fields, and never carrying the password.
  await expect(page.getByTestId("connector-url")).toHaveValue(
    new RegExp(`^postgresql://${DATABASE.user}@${DATABASE.host}:${DATABASE.port}/`)
  )
  await expect(page.getByTestId("connector-url")).not.toHaveValue(
    new RegExp(DATABASE.password === "" ? "\\u0000never" : DATABASE.password)
  )
  await expectFieldActionAligned(page.getByTestId("connector-url"), page.getByTestId("copy-url"))
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, postgres)).toBeVisible()

  // And it is there the moment a stored connection is opened. The password
  // never comes back, so a form that waited for one to be typed showed
  // nothing at all — while the server fills it in from what it has stored.
  await editConnector(page, postgres)
  await expect(page.getByTestId("connector-url")).toHaveValue(
    new RegExp(`^postgresql://${DATABASE.user}@${DATABASE.host}:${DATABASE.port}/`)
  )
  await page.getByRole("button", { name: "Cancel" }).click()

  // A personal directory is not addressed by a URL: the source does not
  // implement the capability, the server answers 501, and the row is absent.
  await pickAdapterType(page, "file")
  await page.getByTestId("connector-name").fill(files)
  await expect(page.getByTestId("connector-url")).toHaveCount(0)
  await page.getByTestId("save-connector").click()
  await expect(connectorRow(page, files)).toBeVisible()

  await deleteConnector(page, postgres)
  await deleteConnector(page, files)
})

test("an address is laid out on one line, because the options model says so", async ({
  page,
}) => {
  await login(page)
  await pickAdapterType(page, "postgres")

  const host = await page.getByTestId("field-host").boundingBox()
  const port = await page.getByTestId("field-port").boundingBox()
  const database = await page.getByTestId("field-database").boundingBox()

  const middle = (box: { y: number; height: number } | null) =>
    box === null ? 0 : box.y + box.height / 2

  // Host and port share a row; the database begins the next one.
  expect(Math.abs(middle(host) - middle(port))).toBeLessThan(4)
  expect(middle(database)).toBeGreaterThan(middle(host) + 8)
  expect(port?.x ?? 0).toBeGreaterThan(host?.x ?? 0)
})

test("asks before throwing away changes that were never applied", async ({ page }) => {
  const name = `e2e-win-dirty-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await editConnector(page, name)
  await page.getByTestId("connector-name").fill(`${name}-edited`)

  // The cross, not Cancel: Cancel says "discard" out loud, the cross does not.
  await page.locator('[data-testid^="window-close-connector"]').first().click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await page.getByTestId("confirm-accept").click()
  await expect(windows(page)).toHaveCount(0)

  // Nothing was saved, so the row still carries the name it had.
  await expect(connectorRow(page, name)).toBeVisible()

  await deleteConnector(page, name)
})

test("closes without a word when nothing was changed", async ({ page }) => {
  // Filling the form in is a change made by this window, not by the user, and
  // a question asked every time one is closed teaches people to answer it
  // without reading.
  const name = `e2e-win-clean-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await editConnector(page, name)
  await expect(page.getByTestId("connector-name")).toHaveValue(name)
  // Long enough for everything the window does on its own — reading the
  // schema, filling the fields, asking for the connection string.
  await expect(page.getByTestId("connector-url")).not.toHaveValue("")

  // Nor is looking at the password: the stand-in gives way and comes back,
  // and none of that is a value anybody changed.
  await page.getByTestId("field-password").click()
  await page.getByTestId("field-user").click()
  await expect(page.getByTestId("field-password")).toHaveValue("<hidden>")

  await page.locator('[data-testid^="window-close-connector"]').first().click()
  await expect(windows(page)).toHaveCount(0)
  await expect(page.getByTestId("confirm-accept")).toHaveCount(0)

  await deleteConnector(page, name)
})

test("a value typed and then put back is not a change", async ({ page }) => {
  const name = `e2e-win-undone-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await editConnector(page, name)
  await page.getByTestId("connector-name").fill(`${name}-edited`)
  await page.getByTestId("connector-name").fill(name)

  await page.locator('[data-testid^="window-close-connector"]').first().click()
  await expect(windows(page)).toHaveCount(0)
  await expect(page.getByTestId("confirm-accept")).toHaveCount(0)

  await deleteConnector(page, name)
})
