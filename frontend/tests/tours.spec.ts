import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"
import { runOnce } from "./utils/pipelines"

/**
 * The short tours (D356), started from Preferences and followed the way a
 * person follows them: by pressing whatever the ring stands around.
 */

const position = (page: Page) => page.getByTestId("tour-position")
const ring = (page: Page) => page.getByTestId("tour-ring")

/** The middle of the ring: the control the chapter points at. */
async function ringed(page: Page): Promise<{ x: number; y: number }> {
  let box: { x: number; y: number; width: number; height: number } | null = null
  await expect(async () => {
    // Settled: the ring glides between controls.
    const first = await ring(page).boundingBox()
    await page.waitForTimeout(250)
    box = await ring(page).boundingBox()
    expect(box).not.toBeNull()
    expect(first).toEqual(box)
  }).toPass({ timeout: 10_000 })
  const settled = box as unknown as { x: number; y: number; width: number; height: number }
  return { x: settled.x + settled.width / 2, y: settled.y + settled.height / 2 }
}

async function pressRinged(page: Page) {
  const at = await ringed(page)
  await page.mouse.click(at.x, at.y)
}

/** Follow the ring until the chapter changes, as a person does, a few presses at most. */
async function followTo(page: Page, step: string) {
  for (let press = 0; press < 5; press += 1) {
    if ((await position(page).innerText()) === step) return
    await pressRinged(page)
    await page.waitForTimeout(400)
  }
  await expect(position(page)).toHaveText(step)
}

async function startFromPreferences(page: Page, id: string) {
  await page.goto("/preferences/tours")
  await page.getByTestId(`preference-tour-${id}`).click()
  await page.waitForURL("/")
}

test("the table tour opens a practice table as a chart, a structure and documents, then takes it away", async ({
  page,
}) => {
  test.setTimeout(90_000)
  await login(page)
  await startFromPreferences(page, "views")
  await expect(position(page)).toHaveText("Step 1 of 4")
  const practice = page.locator('[data-testid^="connector-practice"]')

  await followTo(page, "Step 2 of 4") // the practice connection, then tasks
  await followTo(page, "Step 3 of 4") // chart
  await followTo(page, "Step 4 of 4") // back to tasks, structure
  await pressRinged(page) // back to tasks, documents
  for (let press = 0; press < 3 && !(await page.getByTestId("tour-finish").isVisible()); press += 1) {
    await pressRinged(page)
    await page.waitForTimeout(400)
  }
  await expect(page.getByTestId("tour-finish")).toBeVisible()
  await page.screenshot({ path: test.info().outputPath("views-finished.png") })

  const before = await practice.count()
  await page.getByTestId("tour-finish").click()
  await expect(page.getByTestId("tour-hint")).toHaveCount(0)
  await expect.poll(() => practice.count()).toBe(before - 1)
})

test("the pipeline tour saves the practice table as a CSV in the person's folder", async ({ page }) => {
  test.setTimeout(120_000)
  await login(page)
  await startFromPreferences(page, "pipeline")
  await expect(position(page)).toHaveText("Step 1 of 6")

  await pressRinged(page) // Pipelines
  await expect(page.getByTestId("pipelines-space")).toBeVisible()
  await pressRinged(page) // a new pipeline
  await expect(position(page)).toHaveText("Step 2 of 6")
  await pressRinged(page) // the practice database in the rail
  await expect(page.getByTestId("card-picker")).toBeVisible()
  await pressRinged(page) // main
  await pressRinged(page) // tick tasks
  await pressRinged(page) // put it on the canvas
  await expect(position(page)).toHaveText("Step 3 of 6")
  await pressRinged(page) // the folder in the rail
  await pressRinged(page) // tick the folder itself
  await pressRinged(page) // put it on the canvas
  await expect(position(page)).toHaveText("Step 4 of 6")
  // The table's row is ringed: dragged onto the folder's top (D363).
  const from = await ringed(page)
  const top = page.getByTestId("pipeline-canvas").locator('[data-testid^="graph-port-"][data-testid$="-top"]')
  const to = await top.boundingBox()
  if (to === null) throw new Error("The folder's row is not on screen")
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 })
  await expect(top).toHaveClass(/graph-node__row--fit/)
  await page.screenshot({ path: test.info().outputPath("pipeline-drag.png") })
  await page.mouse.up()
  // Dropped, it is saved and its offers asked before the link is drawn.
  await expect(page.getByTestId("link-panel")).toBeVisible({ timeout: 15_000 })
  await expect(position(page)).toHaveText("Step 5 of 6")
  await pressRinged(page) // the menu beside Switch on
  await pressRinged(page) // Run once now
  // A file of that name left by an earlier run: the ring moves to the choice.
  const result = page.getByTestId("link-panel-result")
  await expect(result).toHaveAttribute("data-outcome", /done|failed/, { timeout: 30_000 })
  if ((await result.getAttribute("data-outcome")) === "failed") {
    await pressRinged(page) // If the name is taken
    await page.getByRole("option", { name: "Keep both" }).click()
    await runOnce(page)
  }
  await expect(position(page)).toHaveText("Step 6 of 6", { timeout: 30_000 })
  await pressRinged(page) // back to Data
  await expect(page.getByTestId("pipelines-space")).toHaveCount(0)
  await pressRinged(page) // the folder
  await ringed(page)
  await page.screenshot({ path: test.info().outputPath("pipeline-file.png") })
  await page.getByTestId("tour-next").click()
  await expect(page.getByTestId("tour-hint")).toHaveCount(0)

  // The CSV stays: it is the person's. The practice database goes.
  await expect(page.getByTestId("tour-hint")).toHaveCount(0)
})

test("the dashboards tour points at where dashboards and their metrics come from", async ({ page }) => {
  await login(page)
  await startFromPreferences(page, "dashboards")
  await expect(position(page)).toHaveText("Step 1 of 4")
  await pressRinged(page) // Dashboards
  await expect(position(page)).toHaveText("Step 2 of 4")
  await ringed(page)
  await page.getByTestId("tour-next").click()
  await expect(position(page)).toHaveText("Step 3 of 4")
  // Without a metrics store there are no sources to open, and Next goes on.
  if (await page.getByTestId("agents-open").isVisible()) {
    await pressRinged(page) // Sources
    await expect(page.getByTestId("agents-dialog")).toBeVisible()
    await ringed(page)
    await page.screenshot({ path: test.info().outputPath("dashboards-agent.png") })
  }
  await page.getByTestId("tour-next").click()
  await expect(position(page)).toHaveText("Step 4 of 4")
  if (await page.getByTestId("agents-dialog").isVisible()) {
    await pressRinged(page) // the connections view
    await expect(page.getByTestId("reporting-table")).toBeVisible()
  }
  await page.getByTestId("tour-next").click()
  await expect(page.getByTestId("tour-hint")).toHaveCount(0)
})

test("the agent tour points at its key, its model and what it is given", async ({ page }) => {
  await login(page)
  await startFromPreferences(page, "agent")
  await expect(position(page)).toHaveText("Step 1 of 5")
  await followTo(page, "Step 2 of 5") // AI
  if (!(await page.getByTestId("ai-settings").isVisible())) await pressRinged(page) // settings
  await expect(page.getByTestId("ai-settings")).toBeVisible()
  await ringed(page)
  await page.screenshot({ path: test.info().outputPath("agent-key.png") })
  await page.getByTestId("tour-next").click()
  await expect(position(page)).toHaveText("Step 3 of 5")
  await followTo(page, "Step 4 of 5") // a new chat
  await expect(position(page)).toHaveText("Step 4 of 5")
  await ringed(page)
  await page.getByTestId("tour-next").click()
  await expect(position(page)).toHaveText("Step 5 of 5")
  await ringed(page)
  await page.getByTestId("tour-next").click()
  await expect(page.getByTestId("tour-hint")).toHaveCount(0)
  await page.getByTestId("space-data").click()
})
