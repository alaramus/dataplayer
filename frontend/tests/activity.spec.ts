import { expect, test } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { toast } from "./utils/notices"
import {
  COLLEAGUE_PASSWORD,
  colleagueEmail,
  createColleague,
  removeColleague,
  signInAs,
} from "./utils/people"
import { connectorRow, deleteConnector, editConnector } from "./utils/workspace"

/**
 * The claims about the activity sheet that only a browser can settle (D113,
 * D114). What is in the log, when a card fades and how a section is worded are
 * unit-tested; where a thing is drawn, and over what, is not.
 */

test("draws a message over the window that raised it", async ({ page }) => {
  const name = `e2e-activity-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  // Refused inside the connection's own window, which is where most of this
  // application's messages come from: a card behind that window is not a
  // message at all.
  await page.route("**/api/v1/connectors/check-draft", (route) => route.abort())
  await editConnector(page, name)
  await page.getByTestId("check-draft").click()

  const card = toast(page, "Could not reach the server")
  await expect(card).toBeVisible()
  const box = (await card.boundingBox())!
  const onTop = await page.evaluate(
    ({ x, y }) => document.elementFromPoint(x, y)?.closest('[data-testid="toast"]') !== null,
    { x: box.x + box.width / 2, y: box.y + box.height / 2 }
  )
  expect(onTop).toBe(true)

  await page.unroute("**/api/v1/connectors/check-draft")
  await page.getByTestId("cancel-connector").click()
  await deleteConnector(page, name)
})

test("keeps what was said, shows it in the sheet and stops interrupting on request", async ({ page }) => {
  const name = `e2e-activity-log-${Date.now()}`
  await login(page)
  await createFileConnector(page, name)

  // Saving a connection says so, and that message is still there afterwards:
  // the whole point of recording before showing (D114).
  await expect(toast(page, "Connection saved")).toBeVisible()
  await page.getByTestId("activity-indicator").click()
  const sheet = page.getByTestId("activity-panel")
  await expect(sheet.getByTestId("notice").filter({ hasText: "Connection saved" })).toHaveCount(1)
  // Opening the sheet takes the cards down: it is now saying it properly.
  await expect(page.getByTestId("toast")).toHaveCount(0)

  // The sheet floats over the work rather than moving it: nothing behind it
  // changes width when it opens.
  const before = (await page.getByTestId("app-footer").boundingBox())!.width
  await page.getByTestId("do-not-disturb").click()
  expect((await page.getByTestId("app-footer").boundingBox())!.width).toBe(before)

  await page.keyboard.press("Escape")
  await expect(sheet).toHaveCount(0)
  await editConnector(page, name)
  await page.getByTestId("connector-name").fill(`${name}-again`)
  await page.getByTestId("save-connector").click()

  // Not disturbed, but recorded all the same.
  await expect(page.getByTestId("toast")).toHaveCount(0)
  await page.getByTestId("activity-indicator").click()
  await expect(sheet.getByTestId("notice").filter({ hasText: "Connection saved" })).toHaveCount(2)
  await page.keyboard.press("Escape")

  await deleteConnector(page, `${name}-again`)
})

test("stops offering a request whose connection has gone", async ({ page, browser }) => {
  const email = colleagueEmail()
  const name = `e2e-gone-${Date.now()}`

  await login(page)
  await createColleague(page, email)
  await createPostgresConnector(page, name)
  await connectorRow(page, name).click()
  await pickSchema(page, "demo_lab")
  await openNode(page, "projects")
  await page.getByTestId("grid-share").click()
  const link = await page.getByTestId("share-link").inputValue()
  await page.getByTestId("share-close").click()

  const theirs = await browser.newContext({ baseURL: new URL(link).origin })
  const colleague = await theirs.newPage()
  try {
    await signInAs(colleague, email, COLLEAGUE_PASSWORD)
    await colleague.goto(new URL(link).pathname)
    await colleague.getByTestId("share-request").click()
    await expect(colleague.getByTestId("share-requested")).toBeVisible()

    await page.getByTestId("activity-indicator").click()
    const sheet = page.getByTestId("activity-panel")
    const waiting = sheet
      .locator('[data-testid^="attention-access:"]')
      .filter({ hasText: name })
    await expect(waiting).toHaveCount(1)

    // Deleted where it was deleted for real: in this tab, from the window of
    // the connection itself. The database takes the request with it, and the
    // line about it used to sit in the sheet regardless — with an Open that
    // did nothing at all, which is what a dead button looks like.
    await page.keyboard.press("Escape")
    await deleteConnector(page, name)

    await page.getByTestId("activity-indicator").click()
    await expect(waiting).toHaveCount(0)
    await page.keyboard.press("Escape")
  } finally {
    await theirs.close()
  }

  await removeColleague(page, email)
})
