import { expect, test } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

import { catalogCheck, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/**
 * The diagram, where its claims can be checked.
 *
 * Almost nothing here is provable anywhere else. Where a card sits comes back
 * from a worker; an edge is a curve that has to be picked; the 3D view exists
 * only if this browser can make a WebGL context, and what either presentation
 * is painted with is a question about the cascade. The unit tests know the
 * shapes the producer builds; this knows they arrived on screen.
 */

/** The two tables a scenario asks for, and the third the diagram infers. */
const PROJECTS = "graph-node-demo_lab.projects"
const ORGANIZATIONS = "graph-node-demo_lab.organizations"
const OUTSIDE = "graph-node-demo_lab.app_users"
/** An edge is identified by its table and the key's own name. */
const ORGANIZATION_EDGE = '["demo_lab.projects","projects_organization_id_fkey"]'

/** The card's header, which is what a user grabs and what names the node. */
function header(card: Locator, label: string) {
  return card.getByRole("button", { name: label, exact: true })
}

/**
 * Two tables, so that what was asked for and what is merely referenced stay
 * distinguishable: projects points at app_users, which nobody asked to read.
 */
async function openDiagram(page: Page, name: string) {
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await catalogCheck(page, "projects").click()
  await catalogCheck(page, "organizations").click()
  await page.getByTestId("catalog-relationships").click()
  await expect(page.getByTestId("relationship-panel")).toContainText(
    `2 requested tables · ${name}`
  )
  await expect(page.getByTestId(PROJECTS)).toBeVisible()
}

/** What the browser kept of the view: positions, cameras and the mode. */
async function savedView(page: Page) {
  return await page.evaluate(() => {
    const key = Object.keys(localStorage).find((name) => name.startsWith("dataplayer-graph:"))
    if (key === undefined) return null
    return JSON.parse(localStorage.getItem(key) ?? "null") as {
      state: { mode: string; positions3: Record<string, { x: number; y: number; z: number }> }
    } | null
  })
}

async function savedPoint3(page: Page) {
  return (await savedView(page))?.state.positions3["demo_lab.projects"] ?? null
}

/** The middle of an element, and a straight drag from it. */
async function centre(target: Locator) {
  const box = await target.boundingBox()
  if (box === null) throw new Error("the element has no rectangle")
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 }
}

async function dragBy(page: Page, target: Locator, dx: number, dy: number) {
  const from = await centre(target)
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x + dx, from.y + dy, { steps: 8 })
  await page.mouse.up()
}

test("draws the checked tables, the keys between them and what they point at", async ({
  page,
}) => {
  const name = `e2e-graph-${Date.now()}`
  await openDiagram(page, name)

  // Three cards for two tables: the table the selection points at is drawn as
  // a placeholder rather than left out, and both declared keys are drawn.
  const viewer = page.getByTestId("graph-viewer")
  await expect(viewer).toContainText("3 nodes · 2 connections")
  await expect(page.getByTestId(OUTSIDE)).toContainText("Outside selection")

  // Both themes reach the edges, and a token nothing reads changes nothing: the
  // question is what the curve is painted with, not what is declared. The
  // painted path is the one the focusable hit path lies over, and it is asked
  // before anything is selected — a selected edge is painted the accent colour.
  const painted = page.getByTestId(ORGANIZATION_EDGE).locator("xpath=./preceding-sibling::path")
  const theme = page.getByTestId("theme-toggle")
  if ((await theme.getAttribute("data-theme")) === "dark") await theme.click()
  await expect(theme).toHaveAttribute("data-theme", "light")
  await expect(painted).toHaveCSS("stroke", "rgb(115, 134, 158)")
  await theme.click()
  await expect(theme).toHaveAttribute("data-theme", "dark")
  await expect(painted).toHaveCSS("stroke", "rgb(132, 153, 182)")

  // A field is what an edge attaches to, so it is a thing to select, and what
  // it answers is the keys on that field alone.
  await page.getByTestId("graph-port-demo_lab.projects-owner_id").click()
  const inspector = page.getByTestId("graph-inspector")
  await expect(inspector).toContainText("projects_owner_id_fkey")
  await expect(inspector).not.toContainText("projects_organization_id_fkey")

  // The other key is taken the way a pointer cannot take a hairline: the curve
  // is focusable, and Enter on it selects the relationship it draws.
  await page.getByTestId(ORGANIZATION_EDGE).press("Enter")
  await expect(inspector).toContainText("organization_id → organization_id")
  await expect(inspector).toContainText("cascade")

  // Collapsing the fields keeps every connection, moved onto the headers.
  await page.getByTestId("graph-details-toggle").click()
  await expect(page.getByTestId("graph-port-demo_lab.projects-owner_id")).toHaveCount(0)
  await expect(page.getByTestId(ORGANIZATION_EDGE)).toHaveCount(1)
  await page.getByTestId("graph-details-toggle").click()
  await expect(page.getByTestId("graph-port-demo_lab.projects-owner_id")).toBeVisible()

  // Moving a card changes the layout and nothing else, and the layout outlives
  // the page: it is written for this user, this connection and this selection.
  const card = page.getByTestId(PROJECTS)
  const placed = () => card.evaluate((node) => getComputedStyle(node).left)
  const before = await placed()
  await dragBy(page, header(card, "projects"), 70, 40)
  const moved = await placed()
  expect(moved).not.toBe(before)

  await page.reload()
  await expect(card).toBeVisible()
  await expect(card).toHaveCSS("left", moved)

  // The diagram is a way into the data, not a place the data lives.
  await header(card, "projects").click()
  await page.getByTestId("graph-open-table").click()
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(rowsTabs(page).first()).toContainText("projects")
  await expect(page.getByTestId("row-grid")).toBeVisible()

  await deleteConnector(page, name)
})

test("carries one selection into 3D, into a window and through a reload", async ({
  page,
}) => {
  const name = `e2e-graph-3d-${Date.now()}`
  await openDiagram(page, name)

  // Selecting in one presentation and reading it in the other is the whole
  // claim that the two renderers share one document.
  await header(page.getByTestId(ORGANIZATIONS), "organizations").click()
  await expect(page.getByTestId("graph-inspector")).toContainText("organizations")

  await page.getByTestId("graph-mode-3d").click()
  const canvas = page.getByTestId("graph-3d-canvas")
  await expect(canvas).toBeVisible()
  expect(
    await canvas.evaluate((node) => (node as HTMLCanvasElement).getContext("webgl2") !== null)
  ).toBe(true)
  await expect(page.getByTestId("graph-inspector")).toContainText("organizations")

  // Search puts a node in front of the camera, which is what makes the next
  // step an answer about picking rather than about aim: the middle of the
  // canvas is that node, so a click there either hits it or clears everything.
  await page.getByTestId("graph-search").fill("projects")
  await page
    .getByRole("list", { name: "Matching nodes" })
    .getByRole("button", { name: "projects", exact: true })
    .click()
  await expect(page.getByTestId("graph-inspector")).toContainText("projects")
  await canvas.click()
  await expect(page.getByTestId("graph-inspector")).toContainText("projects")

  // Shift-drag moves the node on the plane facing the camera. It is a layout
  // edit like the 2D one, so it is written down the same way.
  const middle = await centre(canvas)
  const before = await savedPoint3(page)
  await page.keyboard.down("Shift")
  await page.mouse.move(middle.x, middle.y)
  await page.mouse.down()
  await page.mouse.move(middle.x + 90, middle.y + 60, { steps: 8 })
  await page.mouse.up()
  await page.keyboard.up("Shift")
  await expect.poll(() => savedPoint3(page)).not.toEqual(before)

  // Detaching carries the live panel, so the scene is neither rebuilt nor
  // dropped: the same selection, drawing into the window's own rectangle.
  const tab = page.locator('[data-testid^="workspace-tab-relationships:"]').first()
  const preview = page.getByTestId("workspace-detach-target")
  const from = await centre(tab)
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x, from.y - 24, { steps: 4 })
  await expect(preview).toBeVisible()
  const target = await preview.boundingBox()
  if (target === null) throw new Error("the header drop target has no rectangle")
  await page.mouse.move(target.x + 80, target.y + target.height / 2, { steps: 6 })
  await page.mouse.up()

  const floating = page.getByRole("dialog", { name: `Relationships · ${name}` })
  await expect(floating).toBeVisible()
  await expect(floating.getByTestId("graph-inspector")).toContainText("projects")
  const inWindow = floating.getByTestId("graph-3d-canvas")
  await expect(inWindow).toBeVisible()
  expect(await inWindow.evaluate((node) => (node as HTMLCanvasElement).width)).toBeGreaterThan(0)

  await floating.getByTestId("dock-panel").click()
  await expect(floating).toHaveCount(0)
  await expect(canvas).toBeVisible()

  // A reload restores the presentation, the camera and where the node was put:
  // it is still under the point it was dragged to, so clicking there picks it.
  await page.reload()
  await expect(page.getByTestId("graph-mode-3d")).toHaveAttribute("aria-pressed", "true")
  await expect(canvas).toBeVisible()
  const restored = await centre(canvas)
  await page.mouse.click(restored.x + 90, restored.y + 60)
  await expect(page.getByTestId("graph-inspector")).toContainText("projects")

  await deleteConnector(page, name)
})
