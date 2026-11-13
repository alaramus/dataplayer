import type { Locator, Page } from "@playwright/test"

/** A row of a card on the pipeline canvas, found by its text. */
export function canvasRow(page: Page, text: string): Locator {
  return page.getByTestId("pipeline-canvas").locator('[data-testid^="graph-port-"]', { hasText: text })
}

/** A row dragged onto another with the mouse, as a person draws a link. */
export async function drawLink(page: Page, from: Locator, to: Locator) {
  const start = await from.boundingBox()
  const end = await to.boundingBox()
  if (start === null || end === null) throw new Error("A row to join is not on screen")
  await page.mouse.move(start.x + start.width / 2, start.y + start.height / 2)
  await page.mouse.down()
  await page.mouse.move(end.x + end.width / 2, end.y + end.height / 2, { steps: 12 })
  await page.mouse.up()
}

/** Run once now, from the menu beside Switch on (D362). */
export async function runOnce(page: Page) {
  await page.getByTestId("pipeline-run-menu").click()
  await page.getByTestId("menu-item-run-once").click()
}

/** The schedule's window, from the menu beside Switch on. */
export async function openSchedule(page: Page) {
  await page.getByTestId("pipeline-run-menu").click()
  await page.getByTestId("menu-item-schedule").click()
}

/** A line of the pipeline's "⋯" menu: its history, renaming it, or deleting it. */
export async function pipelineMenu(page: Page, item: "history" | "rename" | "delete") {
  await page.getByTestId("pipeline-more").click()
  await page.getByTestId(`menu-item-${item}`).click()
}
