import type { Page } from "@playwright/test"

/**
 * Reaching the parts of the catalog column.
 *
 * The catalog is a list of one level: a row is opened by clicking it and
 * picked out by its tick box, and everything that can be done to what is
 * picked lives in one menu in the head.
 */
export function catalogRow(page: Page, label: string) {
  return page.getByTestId(`catalog-node-${label}`)
}

export function catalogCheck(page: Page, label: string) {
  return page.getByTestId(`catalog-check-${label}`)
}

/** Open a row: a directory is walked into, anything readable opens a tab. */
export async function openNode(page: Page, label: string) {
  await catalogRow(page, label).click()
}

export async function catalogAction(page: Page, action: string) {
  await page.getByTestId("catalog-actions").click()
  await page.getByTestId(`menu-item-${action}`).click()
}

/** Which groupings the list is showing, for a source that has any. */
export async function pickSchema(page: Page, schema: string) {
  await page.getByTestId("catalog-groups").click()
  await page.getByRole("option", { name: schema, exact: true }).click()
  // The menu stays open for a multiple select: it is closed the way a user
  // closes it, by pressing Escape.
  await page.keyboard.press("Escape")
}
