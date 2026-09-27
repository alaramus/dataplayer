import { expect } from "@playwright/test"
import type { Locator, Page } from "@playwright/test"

/**
 * The rows of the AI history, once both of its lists have arrived.
 *
 * A count taken while it loads is zero, whatever the history holds.
 */
export async function historyRows(page: Page): Promise<Locator> {
  await expect(page.getByTestId("ai-history")).toHaveAttribute("aria-busy", "false")
  return page.locator('[data-testid^="ai-chat-row-"]')
}
