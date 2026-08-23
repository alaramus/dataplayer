import { expect, test } from "@playwright/test"

import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema } from "./utils/catalog"
import {
  catalogTab,
  deleteConnector,
  connectorRow,
  openConnector,
  rowsTabs,
} from "./utils/workspace"

/**
 * The engine is exercised on its own route with placeholder panels: nothing
 * here touches a connector, so a failure is a failure of the layout and not of
 * the data behind it.
 */

test("resizes, collapses and remembers the layout", async ({ page }) => {
  await page.goto("/workspace-demo")

  const alpha = page.getByTestId("workspace-leaf-left")
  const before = (await alpha.boundingBox())?.width ?? 0
  expect(before).toBeGreaterThan(0)

  const separator = page.getByTestId("workspace-separator").first()
  const box = await separator.boundingBox()
  if (box === null) throw new Error("the separator has no box")
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 10 })
  await page.mouse.up()

  const after = (await alpha.boundingBox())?.width ?? 0
  expect(after).toBeGreaterThan(before + 50)

  await page.reload()
  const restored = (await alpha.boundingBox())?.width ?? 0
  expect(Math.abs(restored - after)).toBeLessThan(6)

  await page.getByTestId("workspace-collapse-left").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeLessThan(48)

  await page.getByTestId("reset-workspace").click()
  expect((await alpha.boundingBox())?.width ?? 0).toBeGreaterThan(50)
})

test("opens a panel as a tab and closes it again", async ({ page }) => {
  await page.goto("/workspace-demo")
  await page.getByTestId("reset-workspace").click()

  await page.getByTestId("open-demo-panel").click()
  const tab = page.getByTestId("workspace-tab-demo-1")
  await expect(tab).toBeVisible()

  await page.getByTestId("workspace-close-demo-1").click()
  await expect(tab).toHaveCount(0)
})

test("drags a tab to an edge and gets a new section", async ({ page }) => {
  await page.goto("/workspace-demo")
  await page.getByTestId("reset-workspace").click()

  const sections = page.locator('[data-testid^="workspace-leaf-"]')
  await expect(sections).toHaveCount(2)

  // Gamma shares a section with beta, so the section it leaves survives and
  // the one it lands in is new. Nothing here is provable in jsdom: the drop
  // zone is decided from a measured rectangle under a captured pointer.
  const tab = page.getByTestId("workspace-tab-gamma")
  const main = page.getByTestId("workspace-leaf-main")
  const from = await tab.boundingBox()
  const onto = await main.boundingBox()
  if (from === null || onto === null) throw new Error("the tab or the section has no box")

  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  // Into the left quarter, and well clear of the top and bottom quarters, so
  // the zone is the left edge and not a corner.
  await page.mouse.move(onto.x + onto.width * 0.1, onto.y + onto.height * 0.6, { steps: 12 })
  await page.mouse.up()

  await expect(sections).toHaveCount(3)
  await expect(main.getByTestId("workspace-tab-gamma")).toHaveCount(0)
  await expect(page.getByTestId("workspace-tab-gamma")).toBeVisible()
  await expect(main.getByTestId("workspace-tab-beta")).toBeVisible()
})

/** A layout a previous run left behind is not the subject of these tests. */
async function freshLayout(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("dataplayer-workspace")
  })
  await page.reload()
}

test("a signed in user lands on three columns, two of them waiting", async ({ page }) => {
  await login(page)
  await freshLayout(page)

  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)
  await expect(page.getByTestId("workspace-tab-connectors")).toBeVisible()
  await expect(page.getByTestId("connector-list")).toBeVisible()

  // The two columns nothing has been opened in are there and say what belongs
  // in them, which is the whole point of a pinned section.
  await expect(page.getByTestId("navigate-empty")).toBeVisible()
  await expect(page.getByTestId("work-empty")).toBeVisible()

  // The panel of connections has nothing to close: a column that could be
  // emptied with no way back is not a column.
  await expect(page.getByTestId("workspace-close-connectors")).toHaveCount(0)

  // The screen is closed at the bottom by a bar of its own, waiting for what
  // belongs in a status line.
  await expect(page.getByTestId("app-footer")).toBeVisible()

  // The sections fill what the toolbar leaves of the window. A page with its
  // own padding and a height of its own content would leave them floating in
  // it, and a unit test cannot tell the difference.
  const viewport = page.viewportSize()
  if (viewport === null) throw new Error("the page has no viewport")
  const box = await page.getByTestId("workspace").boundingBox()
  if (box === null) throw new Error("the workspace has no box")
  expect(box.width).toBe(viewport.width)
  expect(box.height).toBeGreaterThan(viewport.height - 80)
})

test("a connection fills the middle column, and the next one replaces it", async ({ page }) => {
  const first = `e2e-cols-a-${Date.now()}`
  const second = `e2e-cols-b-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, first)
  await createPostgresConnector(page, second)

  await openConnector(page, first)
  await expect(page.getByTestId("navigate-empty")).toHaveCount(0)
  await expect(catalogTab(page)).toContainText(first)
  await expect(page.getByTestId("catalog-list")).toContainText("connector")

  // One catalog at a time: the middle column is a column, not a stack of them.
  await openConnector(page, second)
  const catalogs = page.locator('[data-testid^="workspace-tab-catalog:"]')
  await expect(catalogs).toHaveCount(1)
  await expect(catalogs).toContainText(second)

  // Closing it leaves the column, with the hint back in it.
  const tab = await catalogTab(page).getAttribute("data-testid")
  if (tab === null) throw new Error("the catalog tab has no test id")
  await page.getByTestId(tab.replace("workspace-tab-", "workspace-close-")).click()
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)
  await expect(page.getByTestId("navigate-empty")).toBeVisible()

  for (const name of [first, second]) {
    await deleteConnector(page, name)
    await expect(connectorRow(page, name)).toHaveCount(0)
  }
})

test("tables stack as tabs in the right column and survive a reload", async ({ page }) => {
  const name = `e2e-cols-rows-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(rowsTabs(page)).toHaveCount(1)
  await openNode(page, "pg_namespace")
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(page.getByTestId("work-empty")).toHaveCount(0)

  // Three columns still, so the tables went beside each other and not on top
  // of the list that opened them.
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)

  await page.reload()
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(page.getByTestId("catalog-list")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a pushed-aside column of sources still opens one of them", async ({ page }) => {
  const name = `e2e-rail-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)

  await page.getByTestId("workspace-collapse-sources").click()
  expect((await page.getByTestId("workspace-leaf-sources").boundingBox())?.width ?? 0)
    .toBeLessThan(48)

  // What survives the width is the icon of the source and the state dot, and
  // pressing the icon does what the row does: it opens the catalog.
  const icon = page.getByTestId(`connector-rail-${name}`)
  await expect(icon).toBeVisible()
  await expect(page.getByTestId(`connector-state-${name}`)).toBeVisible()
  await icon.click()

  await expect(catalogTab(page)).toContainText(name)
  await expect(page.getByTestId("catalog-list")).toContainText("connector")

  await page.getByTestId("workspace-collapse-sources").click()
  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("clears a strip of tabs down to the one being looked at", async ({ page }) => {
  const name = `e2e-close-others-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await openNode(page, "pg_namespace")
  await expect(rowsTabs(page)).toHaveCount(2)

  await page.getByTestId("workspace-close-others-work").click()

  // The one that was showing is the one that stays: the rest go the way a
  // cross would have sent them, one at a time.
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(rowsTabs(page)).toContainText("pg_namespace")
  await expect(page.getByTestId("workspace-close-others-work")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("every column collapses and comes back, and none of them scrolls the page", async ({
  page,
}) => {
  const name = `e2e-collapse-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  // A schema with a hundred and fifty relations in it: a short list would
  // prove nothing about where the scrolling happens.
  await pickSchema(page, "pg_catalog")
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("row-grid")).toContainText("relname")

  // Nothing here is taller than the window: each column scrolls inside itself.
  const scrolls = await page.evaluate(
    () => document.documentElement.scrollHeight > document.documentElement.clientHeight
  )
  expect(scrolls).toBe(false)

  const rows = page.locator(".catalog-list__rows")
  const inner = await rows.evaluate((el) => el.scrollHeight > el.clientHeight)
  expect(inner).toBe(true)

  // The handle that brings a section back is never pushed off the end of a
  // strip twenty-eight pixels wide.
  for (const id of ["sources", "navigate", "work"]) {
    const handle = page.getByTestId(`workspace-collapse-${id}`)
    await handle.click()
    const leaf = await page.getByTestId(`workspace-leaf-${id}`).boundingBox()
    expect(leaf?.width ?? 0).toBeLessThan(48)
    await expect(handle).toBeVisible()
    await handle.click()
    expect((await page.getByTestId(`workspace-leaf-${id}`).boundingBox())?.width ?? 0)
      .toBeGreaterThan(50)
  }

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
