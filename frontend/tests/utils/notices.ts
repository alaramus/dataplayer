import type { Locator, Page } from "@playwright/test"

/**
 * A message the application has just said.
 *
 * One place, because where such a message is drawn is a decision of the
 * application's and not of sixteen tests: it used to be Quasar's notification
 * at the bottom centre and is now a card of ours at the bottom right (D114).
 */
export function toast(page: Page, text: string): Locator {
  return page.getByTestId("toast").filter({ hasText: text })
}
