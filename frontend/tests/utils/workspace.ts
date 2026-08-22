import type { Page } from "@playwright/test"

/**
 * Reaching the parts of the workspace.
 *
 * The screen is three columns that are always there: connections on the left,
 * the catalog of one of them in the middle, and the data of one node on the
 * right, where several tabs can be open at once. The id of a connection comes
 * from the server, so a catalog or a data tab is addressed by the prefix
 * `panels.ts` gives it.
 */
export function connectionsTab(page: Page) {
  return page.getByTestId("workspace-tab-connectors")
}

export function catalogTab(page: Page) {
  return page.locator('[data-testid^="workspace-tab-catalog:"]').first()
}

export function rowsTabs(page: Page) {
  return page.locator('[data-testid^="workspace-tab-rows:"]')
}

/** A row of the connections column, which is how a user finds a connection. */
export function connectorRow(page: Page, name: string) {
  return page.getByTestId(`connector-${name}`)
}

/** Clicking the row loads that connection's catalog into the middle column. */
export async function openConnector(page: Page, name: string) {
  await connectorRow(page, name).click()
}

/**
 * Everything that is not "open this" lives in the menu of the row: the column
 * is too narrow for a button per action.
 */
export async function connectorAction(page: Page, name: string, action: string) {
  await page.getByTestId(`connector-menu-${name}`).click()
  await page.getByTestId(`menu-item-${action}`).click()
}
