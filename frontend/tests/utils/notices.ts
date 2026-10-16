import type { Locator, Page } from "@playwright/test"

/**
 * A message the application has just said.
 *
 * One place, because where such a message is drawn is a decision of the
 * application's and not of sixteen tests: it used to be Quasar's notification
 * at the bottom centre and is now a card of ours at the bottom right (D114).
 */
export function toast(page: Page, text: string | RegExp): Locator {
  return page.getByTestId("toast").filter({ hasText: text })
}

/**
 * Close a card rather than wait for it to fade.
 *
 * It is drawn over everything at the bottom right for five seconds, which is
 * where a grid's pager and a window's buttons are, and a click there waits out
 * the five seconds. "Connection saved" is the one to close after creating a
 * connection.
 */
export async function dismissToast(page: Page, text: string) {
  await toast(page, text).getByRole("button", { name: "Dismiss", exact: true }).click()
}
