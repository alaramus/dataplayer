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
/** Their column has a head of commands rather than a tab. */
export function connectionsHead(page: Page) {
  return page.getByTestId("connectors-head")
}

export function catalogTab(page: Page) {
  return page.locator('[data-testid^="workspace-tab-catalog:"]').first()
}

export function catalogTabIcon(page: Page) {
  return page.locator('[data-testid^="workspace-tab-icon-catalog:"]').first()
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
 * Everything that is not "open this" lives inside the window the icon opens:
 * checking the connection, editing it and deleting it.
 */
export async function editConnector(page: Page, name: string) {
  await page.getByTestId(`connector-edit-${name}`).click()
}

export async function deleteConnector(page: Page, name: string) {
  await editConnector(page, name)
  await page.locator('[data-testid="delete-connector"][tabindex="0"]').click()
  await page.getByTestId("confirm-accept").click()
}

/**
 * Close a form that opens as a floating window, the way a user does.
 *
 * Every transient form in the application is a window now, and a window is
 * closed by the cross in its bar rather than by Escape — the same as the
 * connection window beside it. The frame builds its id from the dialog's own
 * test id, so the prefix is what a test can hold on to.
 */
export async function closeWindowDialog(page: Page, testId: string) {
  await page.locator(`[data-testid^="window-close-dialog:${testId}"]`).click()
}
