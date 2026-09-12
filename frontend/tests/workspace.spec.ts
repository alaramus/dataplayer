import { expect, test } from "@playwright/test"

import type { Locator, Page } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema, pinColumn } from "./utils/catalog"
import {
  catalogTab,
  closeWindowDialog,
  deleteConnector,
  editConnector,
  connectorRow,
  openConnector,
  rowsTabs,
} from "./utils/workspace"

test("detaches through the header, keeps the grid page and dark surface and returns the tab", async ({ page }) => {
  const name = `e2e-detached-${Date.now()}`
  await login(page)
  const theme = page.getByTestId("theme-toggle")
  if (await theme.getAttribute("data-theme") === "light") await theme.click()
  await expect(theme).toHaveAttribute("data-theme", "dark")
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("grid-next")).toBeEnabled()
  const surface = await page.getByTestId("grid-column-relname")
    .evaluate((node) => getComputedStyle(node).backgroundColor)
  await expect(page.getByTestId("row-grid")).toHaveCSS("background-color", surface)
  const firstPage = await page.getByTestId("grid-page-range").innerText()
  await page.getByTestId("grid-next").click()
  await expect(page.getByTestId("grid-page-range")).not.toHaveText(firstPage)
  await expect(page.getByTestId("grid-page-range")).not.toHaveText("Rows 0")
  const range = await page.getByTestId("grid-page-range").innerText()
  const tab = rowsTabs(page).first()
  const preview = page.getByTestId("workspace-detach-target")

  const carryToHeader = async () => {
    const from = await tab.boundingBox()
    if (from === null) throw new Error("The table tab has no rectangle")
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
    await page.mouse.down()
    await page.mouse.move(from.x + from.width / 2, from.y - 12, { steps: 4 })
    await expect(preview).toBeVisible()
    const target = await preview.boundingBox()
    if (target === null) throw new Error("The header drop target has no rectangle")
    await page.mouse.move(target.x + 80, target.y + target.height / 2, { steps: 6 })
    await expect(preview).toContainText("Drop here to open in a window")
    await expect(preview).toHaveCSS("border-top-style", "solid")
  }

  await carryToHeader()
  await page.keyboard.press("Escape")
  await page.mouse.up()
  await expect(preview).toHaveCount(0)
  await expect(tab).toBeVisible()
  await expect(page.getByRole("dialog", { name: "pg_class", exact: true })).toHaveCount(0)

  await carryToHeader()
  await page.mouse.up()
  const floating = page.getByRole("dialog", { name: "pg_class", exact: true })
  await expect(floating).toBeVisible()
  await expect(tab).toHaveCount(0)
  await expect(floating.getByTestId("grid-page-range")).toHaveText(range)
  // The window has its own raised surface; ordinary cells must keep the
  // docked grid's background instead of showing that through transparent rows.
  await expect(floating).not.toHaveCSS("background-color", surface)
  await expect(floating.getByTestId("row-grid")).toHaveCSS("background-color", surface)
  await expect(floating.getByTestId("grid-column-relname")).toHaveCSS("background-color", surface)
  await floating.getByRole("button", { name: "Maximize", exact: true }).click()
  await floating.getByRole("button", { name: "Minimize", exact: true }).click()
  // Put aside, it is on the taskbar at the foot of the screen and nowhere
  // else, which is the way back to it.
  await page
    .getByTestId("window-taskbar")
    .getByRole("button", { name: "pg_class", exact: true })
    .click()
  await expect(floating.getByTestId("grid-page-range")).toHaveText(range)
  await floating.getByRole("button", { name: "Return to panel", exact: true }).click()
  await expect(floating).toHaveCount(0)
  await expect(tab).toBeVisible()
  await expect(page.getByTestId("grid-page-range")).toHaveText(range)
  await expect(page.getByTestId("row-grid")).toHaveCSS("background-color", surface)

  await carryToHeader()
  await page.mouse.up()
  await expect(floating).toBeVisible()
  await page.reload()
  await expect(tab).toBeVisible()
  await expect(floating).toHaveCount(0)
  await deleteConnector(page, name)
})

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

  // Three: two with panels in them and the one that is there before anything
  // is opened in it.
  const sections = page.locator('[data-testid^="workspace-leaf-"]')
  await expect(sections).toHaveCount(3)

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

  await expect(sections).toHaveCount(4)
  await expect(main.getByTestId("workspace-tab-gamma")).toHaveCount(0)
  await expect(page.getByTestId("workspace-tab-gamma")).toBeVisible()
  await expect(main.getByTestId("workspace-tab-beta")).toBeVisible()
})

test("drops a tab where it is aimed in a strip, not at the end of it", async ({
  page,
}) => {
  await page.goto("/workspace-demo")
  await page.getByTestId("reset-workspace").click()

  // Beta and gamma share a section, in that order. Dragging gamma onto the
  // left half of beta means "before beta", and that used to land at the end
  // however carefully it was aimed. Only a browser can say: the place is read
  // from measured tab rectangles under a captured pointer.
  const main = page.getByTestId("workspace-leaf-main")
  const order = () =>
    main.locator('button[data-testid^="workspace-tab-"]').evaluateAll((tabs) =>
      tabs.map((tab) => (tab as HTMLElement).dataset.testid ?? "")
    )
  expect(await order()).toEqual(["workspace-tab-beta", "workspace-tab-gamma"])

  const gamma = await page.getByTestId("workspace-tab-gamma").boundingBox()
  const beta = await page.getByTestId("workspace-tab-beta").boundingBox()
  if (gamma === null || beta === null) throw new Error("a tab has no box")

  await page.mouse.move(gamma.x + gamma.width / 2, gamma.y + gamma.height / 2)
  await page.mouse.down()
  await page.mouse.move(beta.x + beta.width * 0.2, beta.y + beta.height / 2, { steps: 12 })
  await expect(page.getByTestId("workspace-tab-insertion")).toBeVisible()
  await page.mouse.up()

  expect(await order()).toEqual(["workspace-tab-gamma", "workspace-tab-beta"])
})

/** A layout a previous run left behind is not the subject of these tests. */
async function freshLayout(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("dataplayer-workspace")
  })
  await page.reload()
}

test("a signed in user lands on the columns that have something in them", async ({ page }) => {
  // The list is drawn only when it holds something, and no setup step creates a
  // connection: the scenario brings its own instead of relying on one left behind.
  const name = `e2e-landing-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)
  await freshLayout(page)

  // Two columns, not three: the middle one appears together with a catalog,
  // and a screen of blank columns looks broken rather than empty. See P4.
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(2)
  await expect(page.getByTestId("workspace-leaf-navigate")).toHaveCount(0)
  await expect(page.getByTestId("workspace-tab-connectors")).toBeVisible()
  await expect(page.getByTestId("connector-list")).toBeVisible()

  // The right-hand column is always there, and what stands in it says what to
  // do next rather than naming the column.
  await expect(page.getByTestId("workspace-scene")).toBeVisible()

  // The panel of connections has nothing to close: a column that could be
  // emptied with no way back is not a column.
  await expect(page.getByTestId("workspace-close-connectors")).toHaveCount(0)

  // The screen is closed at the bottom by a bar of its own, waiting for what
  // belongs in a status line.
  await expect(page.getByTestId("app-footer")).toBeVisible()

  // The sections fill the framed work area that the toolbar and status line
  // leave behind. The small inset belongs to the application chrome: it joins
  // the header, workspace and footer into one shell instead of leaving three
  // unrelated edge-to-edge rectangles.
  const viewport = page.viewportSize()
  if (viewport === null) throw new Error("the page has no viewport")
  const workspace = page.getByTestId("workspace")
  const box = await workspace.boundingBox()
  if (box === null) throw new Error("the workspace has no box")
  expect(box.x).toBeGreaterThan(0)
  expect(box.width).toBeLessThan(viewport.width)
  expect(box.height).toBeGreaterThan(viewport.height - 100)
  // The corners belong to each section now: the workspace is the ground they
  // stand on rather than a frame drawn around all of them.
  expect(
    await page
      .getByTestId("workspace-leaf-sources")
      .evaluate((node) => getComputedStyle(node).borderRadius)
  ).not.toBe("0px")
  await deleteConnector(page, name)
})

test("catalogs stand beside each other, and each connection opens once", async ({ page }) => {
  const first = `e2e-cols-a-${Date.now()}`
  const second = `e2e-cols-b-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, first)
  await createPostgresConnector(page, second)

  // The middle column arrives with the first catalog, and the screen is three
  // columns from there on.
  await openConnector(page, first)
  await expect(page.getByTestId("workspace-leaf-navigate")).toBeVisible()
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)
  await expect(catalogTab(page)).toContainText(first)
  await expect(page.getByTestId("catalog-list")).toContainText("connector")

  // As many catalogs as were opened - see P6.
  const catalogs = page.locator('[data-testid^="workspace-tab-catalog:"]')
  await openConnector(page, second)
  await expect(catalogs).toHaveCount(2)

  // Pressing the same connection again brings its tab forward rather than
  // opening a second one: a panel is identified by what it shows.
  await openConnector(page, first)
  await expect(catalogs).toHaveCount(2)

  // Where a catalog had got to survives being switched away from: the section
  // keeps the panel of an inactive tab alive.
  await pickSchema(page, "pg_catalog")
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")
  await catalogs.filter({ hasText: second }).click()
  await expect(page.getByTestId("catalog-list")).not.toContainText("pg_class")
  await catalogs.filter({ hasText: first }).click()
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")

  // Closing the last of them takes the column off the screen again.
  for (const name of [first, second]) {
    const tab = await catalogs.filter({ hasText: name }).getAttribute("data-testid")
    if (tab === null) throw new Error("the catalog tab has no test id")
    await page.getByTestId(tab.replace("workspace-tab-", "workspace-close-")).click()
  }
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(2)
  await expect(page.getByTestId("workspace-scene")).toBeVisible()

  for (const name of [first, second]) {
    await deleteConnector(page, name)
    await expect(connectorRow(page, name)).toHaveCount(0)
  }
})

test("the scene says what to do at each stage", async ({ page }) => {
  const name = `e2e-scene-${Date.now()}`
  await login(page)
  await freshLayout(page)

  // With nothing to connect to. The list is answered for here rather than
  // emptied on the server: every scenario shares one account.
  await page.route(
    (url) => url.pathname === "/api/v1/connectors/",
    async (route) => {
      if (route.request().method() !== "GET") return await route.fallback()
      await route.fulfill({ json: { data: [], count: 0 } })
    }
  )
  await page.reload()
  await expect(page.getByTestId("workspace-scene")).toHaveAttribute("data-stage", "no-connections")

  // A real button, here, rather than a line pointing at the plus on the left.
  await page.getByTestId("scene-add-connector").click()
  await expect(page.getByTestId("adapter-catalog")).toBeVisible()
  await closeWindowDialog(page, "adapter-catalog")

  await page.unrouteAll({ behavior: "ignoreErrors" })
  await page.reload()
  await createPostgresConnector(page, name)
  await expect(page.getByTestId("workspace-scene")).toHaveAttribute("data-stage", "pick-connection")

  await openConnector(page, name)
  await expect(page.getByTestId("workspace-scene")).toHaveAttribute("data-stage", "pick-node")

  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("workspace-scene")).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the list says which connections are open and which is being read", async ({ page }) => {
  const first = `e2e-open-a-${Date.now()}`
  const second = `e2e-open-b-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, first)
  await createPostgresConnector(page, second)

  await openConnector(page, first)
  await openConnector(page, second)

  // Both are open, and the one whose catalog is showing says so fully. See P7.
  await expect(connectorRow(page, first)).toHaveClass(/connector-list__row--open/)
  await expect(connectorRow(page, second)).toHaveClass(/connector-list__row--selected/)

  await page.locator('[data-testid^="workspace-tab-catalog:"]').filter({ hasText: first }).click()
  await expect(connectorRow(page, first)).toHaveClass(/connector-list__row--selected/)
  await expect(connectorRow(page, second)).not.toHaveClass(/connector-list__row--selected/)
  await expect(connectorRow(page, second)).toHaveClass(/connector-list__row--open/)

  for (const name of [first, second]) {
    await deleteConnector(page, name)
    await expect(connectorRow(page, name)).toHaveCount(0)
  }
})

test("a column torn in two leaves no empty half behind", async ({ page }) => {
  const name = `e2e-torn-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await openNode(page, "pg_namespace")
  await expect(rowsTabs(page)).toHaveCount(2)

  // One of the two tables is taken to the bottom of its own column, which
  // splits it: the pinned column keeps the other table.
  const tab = rowsTabs(page).filter({ hasText: "pg_class" })
  const work = page.getByTestId("workspace-leaf-work")
  const from = await tab.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the tab or the column has no box")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width / 2, onto.y + onto.height * 0.9, { steps: 12 })
  await page.mouse.up()
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(4)

  // Closing what the pinned column still held leaves it empty - and its role
  // is being done by the section below it, so it goes off the screen rather
  // than offering to open what is already open.
  const closing = await rowsTabs(page).filter({ hasText: "pg_namespace" }).getAttribute("data-testid")
  if (closing === null) throw new Error("the data tab has no test id")
  await page.getByTestId(closing.replace("workspace-tab-", "workspace-close-")).click()

  await expect(page.getByTestId("workspace-leaf-work")).toHaveCount(0)
  await expect(page.getByTestId("workspace-scene")).toHaveCount(0)
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(page.getByTestId("row-grid")).toBeVisible()

  // And it comes back, with the scene in it, when the last table is closed.
  const last = await rowsTabs(page).getAttribute("data-testid")
  if (last === null) throw new Error("the data tab has no test id")
  await page.getByTestId(last.replace("workspace-tab-", "workspace-close-")).click()
  await expect(page.getByTestId("workspace-leaf-work")).toBeVisible()
  await expect(page.getByTestId("workspace-scene")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("what floats over a panel is drawn over the sticky heading in it", async ({ page }) => {
  const name = `e2e-layer-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await expect(page.getByTestId("row-grid")).toContainText("relname")
  await pinColumn(page, "relname")

  const layerOf = async (locator: Locator) =>
    Number(await locator.first().evaluate((node) => getComputedStyle(node).zIndex))
  const heading = await layerOf(page.getByTestId("grid-column-relname"))
  expect(heading).toBeGreaterThan(0)

  // The scale itself, as the browser resolves it. This is the one place it can
  // be read: a unit test sees an empty string where a `.css` file should be.
  const scale = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement)
    return ["sticky", "overlay", "popover", "window", "drag"].map((name) =>
      Number(style.getPropertyValue(`--dp-layer-${name}`).trim())
    )
  })
  expect(scale.every((value) => Number.isFinite(value) && value > 0)).toBe(true)
  expect([...scale].sort((a, b) => a - b)).toEqual(scale)

  // While a tab is being dragged. The heading of a grid declares a layer of
  // its own, so anything covering the panel has to declare a higher one or it
  // is painted over - which is what left the column names standing out of the
  // drop zone.
  const tab = rowsTabs(page).first()
  const work = page.getByTestId("workspace-leaf-work")
  const from = await tab.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the tab or the column has no box")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width / 2, onto.y + onto.height / 2, { steps: 8 })
  expect(await layerOf(page.locator(".workspace-leaf__overlay"))).toBeGreaterThan(heading)
  await page.mouse.up()

  // And a floating window over the same grid, which is the same question
  // asked once before.
  await editConnector(page, name)
  expect(await layerOf(page.locator(".app-window"))).toBeGreaterThan(heading)

  await page.getByTestId("delete-connector").click()
  await page.getByTestId("confirm-accept").click()
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the head of every column is one height, whatever is in it", async ({ page }) => {
  const name = `e2e-head-${Date.now()}`
  await login(page)
  await freshLayout(page)

  /** The strip of every section on screen, measured where it is drawn. */
  const heights = async () =>
    await page
      .locator(".workspace-leaf__strip")
      .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().height)))

  // A column with a tab beside one with none: the line under them is one line
  // across the screen, or it reads as a broken layout.
  await page.getByTestId("workspace-scene").waitFor()
  const columns = await heights()
  expect(columns).toHaveLength(2)
  expect(new Set(columns).size).toBe(1)

  await createPostgresConnector(page, name)
  await openConnector(page, name)
  expect(new Set(await heights()).size).toBe(1)

  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  expect(new Set(await heights()).size).toBe(1)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("a tab is carried out of its strip and dropped on another one", async ({ page }) => {
  const name = `e2e-carry-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await openNode(page, "pg_namespace")
  await expect(rowsTabs(page)).toHaveCount(2)

  const carried = rowsTabs(page).filter({ hasText: "pg_class" })
  const work = page.getByTestId("workspace-leaf-work")
  const ghost = page.getByTestId("workspace-drag-ghost")
  const from = await carried.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the tab or the column has no box")

  // Pressed and not yet moved: nothing has happened, and the tab is where it
  // was. See G1.
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await expect(ghost).toHaveCount(0)
  await expect(carried).toHaveCount(1)

  // Moved: the tab is in the hand and gone from the strip. See G2.
  await page.mouse.move(onto.x + onto.width / 2, onto.y + onto.height * 0.6, { steps: 10 })
  await expect(ghost).toBeVisible()
  await expect(ghost).toContainText("pg_class")
  await expect(carried).toHaveCount(0)

  // The body of a section divides it, and the middle of the body is not
  // neutral: the nearest edge wins. See G4.
  await page.mouse.up()
  await expect(ghost).toHaveCount(0)
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(4)
  await expect(rowsTabs(page)).toHaveCount(2)

  // And back again by the strip: dropped on the head of the section it came
  // from, it joins the tabs there rather than dividing anything. See G3.
  const home = page.getByTestId("workspace-leaf-work")
  const back = rowsTabs(page).filter({ hasText: "pg_class" })
  const grab = await back.boundingBox()
  const strip = await home.boundingBox()
  if (grab === null || strip === null) throw new Error("no box")
  await page.mouse.move(grab.x + grab.width / 2, grab.y + grab.height / 2)
  await page.mouse.down()
  await page.mouse.move(strip.x + strip.width / 2, strip.y + 15, { steps: 10 })
  await page.mouse.up()

  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)
  await expect(home.locator('[data-testid^="workspace-tab-rows:"]')).toHaveCount(2)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("the tab of connections cannot be taken to another column", async ({ page }) => {
  const name = `e2e-drag-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)

  const tab = page.getByTestId("workspace-tab-connectors")
  const work = page.getByTestId("workspace-leaf-work")
  const from = await tab.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the tab or the column has no box")

  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width / 2, onto.y + onto.height / 2, { steps: 12 })
  // Nothing is offered, so nothing is promised before the button comes up.
  await expect(work.locator(".workspace-leaf__zone")).toHaveCSS("display", "none")
  await page.mouse.up()

  // Still where it was, and the screen is still three columns. See P1 and P3.
  await expect(
    page.getByTestId("workspace-leaf-sources").getByTestId("workspace-tab-connectors")
  ).toBeVisible()
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
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
  await expect(page.getByTestId("workspace-scene")).toHaveCount(0)

  // A data tab is named after the node and nothing else. Whose it is used to
  // stand beside the title; it moved into the tooltip of the icon when that
  // icon started leading back to the catalog — see reveal.spec.ts.
  await expect(rowsTabs(page).first()).toContainText("pg_class")
  await expect(rowsTabs(page).first()).not.toContainText(name)

  // Three columns still, so the tables went beside each other and not on top
  // of the list that opened them.
  await expect(page.locator('[data-testid^="workspace-leaf-"]')).toHaveCount(3)

  await page.reload()
  await expect(rowsTabs(page)).toHaveCount(2)
  await expect(page.getByTestId("catalog-list")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("pushing the column of sources aside takes away the name and nothing else", async ({
  page,
}) => {
  const name = `e2e-rail-same-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, name)

  const box = async (locator: ReturnType<typeof page.getByTestId>) => {
    const found = await locator.boundingBox()
    if (found === null) throw new Error("no box")
    return found
  }

  // Wide: the plus on the left, the icon of the source under it, the state dot
  // on that icon, and the name beside it.
  const plusWide = await box(page.getByTestId("add-connector"))
  const iconWide = await box(page.getByTestId(`connector-edit-${name}`))
  const dotWide = await box(page.getByTestId(`connector-state-${name}`))
  await expect(page.getByTestId(`connector-${name}`)).toContainText(name)

  // The dot sits on the icon rather than at the end of the row.
  expect(dotWide.x).toBeGreaterThan(iconWide.x)
  expect(dotWide.x + dotWide.width).toBeLessThan(iconWide.x + iconWide.width + 2)

  await page.getByTestId("workspace-collapse-sources").click()
  // Wait for the collapse to have happened before measuring anything: a box
  // read while the column is still wide is a race, and this assertion was
  // already at the end of the test doing nothing for it.
  await expect(page.getByTestId("connector-list")).toHaveCount(0)

  const plusNarrow = await box(page.getByTestId("add-connector"))
  const iconNarrow = await box(page.getByTestId(`connector-rail-${name}`))
  const dotNarrow = await box(page.getByTestId(`connector-state-${name}`))

  // Everything stayed where it was; only the name is gone. Two pixels of
  // tolerance, because one layout centres in forty pixels and the other pads
  // by eight.
  expect(Math.abs(plusNarrow.x - plusWide.x)).toBeLessThan(3)
  expect(Math.abs(plusNarrow.y - plusWide.y)).toBeLessThan(3)
  expect(Math.abs(iconNarrow.x - iconWide.x)).toBeLessThan(3)
  expect(Math.abs(iconNarrow.y - iconWide.y)).toBeLessThan(3)
  expect(Math.abs(dotNarrow.x - dotWide.x)).toBeLessThan(3)
  expect(Math.abs(dotNarrow.y - dotWide.y)).toBeLessThan(3)

  await page.getByTestId("workspace-collapse-sources").click()
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

  // And a new connection can still be started from that width. The same test
  // id as the wide column carries, because it is the same action: the strip
  // and the panel stand under v-if/v-else and never exist together.
  await page.getByTestId("add-connector").click()
  await expect(page.getByTestId("adapter-catalog")).toBeVisible()
  await closeWindowDialog(page, "adapter-catalog")
  await expect(page.getByTestId("adapter-catalog")).toHaveCount(0)

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

test("every column goes away and comes back, and none of them scrolls the page", async ({
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

  // The connections narrow to a strip of their own icons, and the handle that
  // brings them back is never pushed off the end of it.
  const narrow = page.getByTestId("workspace-collapse-sources")
  await narrow.click()
  expect((await page.getByTestId("workspace-leaf-sources").boundingBox())?.width ?? 0)
    .toBeLessThan(48)
  await expect(narrow).toBeVisible()
  await narrow.click()
  expect((await page.getByTestId("workspace-leaf-sources").boundingBox())?.width ?? 0)
    .toBeGreaterThan(50)

  // The other two have nothing to show at that width, so they leave the screen
  // for the bar at the foot of it and come back from there with what was in
  // them. The column of work leaves what can be opened in it standing in its
  // place; the catalog gives its room to the columns that are left.
  for (const id of ["navigate", "work"]) {
    const leaf = page.getByTestId(`workspace-leaf-${id}`)
    const wide = (await leaf.boundingBox())?.width ?? 0
    await page.getByTestId(`workspace-aside-${id}`).click()

    const onTheBar = page.getByTestId("workspace-taskbar").getByTestId(`workspace-aside-${id}`)
    await expect(onTheBar).toBeVisible()
    if (id === "navigate") await expect(leaf).toHaveCount(0)
    else await expect(page.getByTestId("workspace-scene")).toBeVisible()

    await onTheBar.click()
    await expect(onTheBar).toHaveCount(0)
    expect((await leaf.boundingBox())?.width ?? 0).toBeGreaterThan(wide - 40)
  }

  // And what was in them is still in them.
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")
  await expect(rowsTabs(page)).toContainText("pg_class")

  // Asking for something that is already in a column on the bar brings the
  // column back: the press used to mark a tab active inside a column nobody
  // could see, and nothing happened at all.
  await page.getByTestId("workspace-aside-navigate").click()
  await expect(page.getByTestId("workspace-leaf-navigate")).toHaveCount(0)
  await openConnector(page, name)
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")
  await expect(
    page.getByTestId("workspace-taskbar").getByTestId("workspace-aside-navigate")
  ).toHaveCount(0)

  // The same for the way back from a table to where it lives.
  await page.getByTestId("workspace-aside-navigate").click()
  await expect(page.getByTestId("workspace-leaf-navigate")).toHaveCount(0)
  await page.getByTestId("panel-reveal").click()
  await expect(page.getByTestId("catalog-list")).toContainText("pg_class")

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})


test("the bar at the foot offers what hangs off nothing else", async ({ page }) => {
  const sql = `e2e-bar-pg-${Date.now()}`
  const files = `e2e-bar-file-${Date.now()}`
  await login(page)
  await freshLayout(page)
  await createPostgresConnector(page, sql)
  await createFileConnector(page, files)

  const bar = page.getByTestId("command-bar")
  const queries = page.getByTestId("command-queries")

  // Nothing is being read, and the library is a person's own: it opens all
  // the same. What acts on a connection lives in that connection's own menu.
  await expect(queries).toBeEnabled()
  await expect(page.getByTestId("command-backups")).toHaveCount(0)

  // A source that runs queries offers the commands. The bar does not repeat
  // which connection they are about — the column and the tab both say it —
  // and each tooltip names it (D69).
  await openConnector(page, sql)
  await expect(bar).not.toContainText(sql)
  await expect(queries).toBeEnabled()
  await queries.hover()
  await expect(page.getByText(`Queries written against ${sql}`)).toBeVisible()

  // And a source that does not run queries keeps the bar's shape: the library
  // stays reachable whatever is open.
  await openConnector(page, files)
  await expect(bar).not.toContainText(files)
  await expect(queries).toBeEnabled()

  // Pressed from the connection, the library opens filtered to it.
  await openConnector(page, sql)
  await queries.click()
  await expect(page.getByTestId("queries-connector")).toContainText(sql)

  for (const name of [sql, files]) {
    await deleteConnector(page, name)
    await expect(connectorRow(page, name)).toHaveCount(0)
  }
})
