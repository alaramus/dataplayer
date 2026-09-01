import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { addFilter, openNode, pickSchema, sortColumn } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import {
  COLLEAGUE_PASSWORD,
  colleagueEmail,
  createColleague,
  removeColleague,
  signInAs,
} from "./utils/people"
import { connectorRow, deleteConnector, editConnector, rowsTabs } from "./utils/workspace"

/**
 * A link to a view, end to end.
 *
 * What cannot be proved anywhere else: the address carries no rights, so the
 * same link answers two different screens depending on who opens it, and the
 * one that opens carries the sender's query and column layout into the
 * reader's own tab. See D58 and D60.
 *
 * The colleague gets a browser of their own rather than a second session in
 * this one. The workspace layout and the state of a grid live in local
 * storage, so signing in as somebody else in the same browser would leave the
 * sender's tabs and the sender's filters on screen — and every assertion below
 * would then pass without a link existing at all.
 */
test("a link shows nothing to a stranger and the sender's view to a colleague", async ({
  page,
  browser,
}) => {
  const email = colleagueEmail()
  const name = `e2e-share-${Date.now()}`

  await login(page)
  await createColleague(page, email)
  await createPostgresConnector(page, name)
  await openProjects(page, name)

  // --- the sender arranges what they are looking at ------------------------
  await addFilter(page, "status", "equals", "active")
  await sortColumn(page, "priority")
  await page.getByTestId("grid-page-size").click()
  await page.getByRole("option", { name: "250", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  await page.getByRole("checkbox", { name: "status", exact: true }).click()
  await page.getByTestId("grid-columns").click()
  const firstName = await page.getByTestId("grid-cell-0-name").innerText()

  // --- and makes an address for it -----------------------------------------
  await page.getByTestId("grid-share").click()
  const link = await page.getByTestId("share-link").inputValue()
  expect(link).toContain("/s/")
  // The dialog itself: an element screenshot waits for it to stop animating,
  // which a page screenshot does not.
  await page.getByTestId("share-dialog").screenshot({ path: "test-results/share-dialog.png" })
  await page.getByTestId("share-close").click()

  const origin = new URL(link).origin
  const path = new URL(link).pathname
  const theirs = await browser.newContext({ baseURL: origin })
  const colleague = await theirs.newPage()

  try {
    // --- somebody without access is told what it is and who to ask ---------
    await signInAs(colleague, email, COLLEAGUE_PASSWORD)
    await colleague.goto(path)
    await expect(colleague.getByTestId("share-no-access")).toContainText(name)
    await colleague
      .getByTestId("share-landing")
      .screenshot({ path: "test-results/share-no-access.png" })
    // The landing screen is a page of its own: the way on is the button it
    // offers, and nothing has been opened.
    await colleague.getByTestId("share-to-workspace").click()
    await colleague.waitForURL("/")
    await expect(rowsTabs(colleague)).toHaveCount(0)

    // --- the owner gives them the connection -------------------------------
    await editConnector(page, name)
    await page.getByTestId("share-connector").click()
    await page.getByTestId("share-user").click()
    await page.getByRole("option", { name: email }).click()
    await page.getByTestId("share-submit").click()
    await expect(page.getByTestId(`share-row-${email}`)).toBeVisible()
    await page.getByTestId("share-close").click()
    await page.getByTestId("cancel-connector").click()

    // --- and now the same link opens the same view -------------------------
    await colleague.goto(path)
    // The address is spent once: the workspace is where the tab lives, and a
    // reload must not open it a second time.
    await colleague.waitForURL("/")
    await expect(rowsTabs(colleague)).toHaveCount(1)
    await expect(colleague.getByTestId("grid-cell-0-name")).toHaveText(firstName)
    // The query travelled: the sort is shown as the sender left it, the page
    // size with it, and a column they hid is not here either.
    await expect(colleague.getByTestId("grid-sort-priority-priority")).toBeVisible()
    await expect(colleague.getByTestId("grid-page-size")).toContainText("250")
    await expect(colleague.getByTestId("grid-column-status")).toHaveCount(0)

    // --- and it lands in the tab they already have open --------------------
    // A tab is one per connection and node, so the second visit brings that
    // one forward and puts the sender's query back into it (D60).
    await colleague.getByTestId("grid-page-size").click()
    await colleague.getByRole("option", { name: "50", exact: true }).click()
    await expect(colleague.getByTestId("grid-page-size")).toContainText("50")
    await colleague.goto(path)
    await colleague.waitForURL("/")
    await expect(rowsTabs(colleague)).toHaveCount(1)
    await expect(colleague.getByTestId("grid-page-size")).toContainText("250")
  } finally {
    await theirs.close()
  }

  // --- clean up after ourselves --------------------------------------------
  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
  await removeColleague(page, email)
})

test("a link that does not exist says so", async ({ page }) => {
  await login(page)
  // A token that was deleted answers the same way, so this screen cannot be
  // used to find out whether one ever existed.
  await page.goto("/s/nosuchtokenatall")
  await expect(page.getByTestId("share-missing")).toBeVisible()
  await page.getByTestId("share-to-workspace").click()
  await page.waitForURL("/")
})

async function openProjects(page: Page, name: string) {
  await connectorRow(page, name).click()
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
}
