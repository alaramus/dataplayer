import type { Page } from "@playwright/test"

/**
 * Getting back to a tab of the workspace.
 *
 * A catalog and a table open as tabs beside the connections, and only the
 * active one is on screen. A user clicks the tab they want back; so does a
 * scenario. The id of a connection is not known here — it comes from the
 * server — so the catalog tab is addressed by the prefix `panels.ts` gives it.
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
