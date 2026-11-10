import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { firstSuperuser, firstSuperuserPassword } from "./config"
import { addFilter } from "./utils/catalog"
import { setTourSeen } from "./utils/onboarding"
import { deleteConnector } from "./utils/workspace"

/**
 * The first-visit welcome and the tour it starts (D355).
 *
 * Every other scenario signs in through `utils/login`, which arrives with
 * the welcome already seen. This one marks it unseen on the account first, to
 * meet it as a first-time visitor does.
 */
async function loginFresh(page: Page) {
  await setTourSeen(page.request, firstSuperuser, firstSuperuserPassword, false)
  await page.goto("/login")
  await page.getByTestId("login-email").fill(firstSuperuser)
  await page.getByTestId("login-password").fill(firstSuperuserPassword)
  await page.getByTestId("login-submit").click()
  await page.waitForURL("/")
}

const hint = (page: Page) => page.getByTestId("tour-hint")

/** The ring stands around the control the chapter is at. */
async function expectRingOn(page: Page, testId: string) {
  const control = page.getByTestId(testId).first()
  await expect(async () => {
    const ring = await page.getByTestId("tour-ring").boundingBox()
    const box = await control.boundingBox()
    expect(ring).not.toBeNull()
    expect(box).not.toBeNull()
    if (ring === null || box === null) return
    expect(ring.x).toBeLessThanOrEqual(box.x)
    expect(ring.y).toBeLessThanOrEqual(box.y)
    expect(ring.x + ring.width).toBeGreaterThanOrEqual(box.x + box.width)
    expect(ring.y + ring.height).toBeGreaterThanOrEqual(box.y + box.height)
  }).toPass({ timeout: 5_000 })
}

test("a first visit opens the welcome, and looking around alone keeps it closed", async ({
  page,
}) => {
  await loginFresh(page)

  await expect(page.getByTestId("onboarding-dialog")).toBeVisible()
  await expect(page.getByTestId("onboarding-theme")).toBeVisible()
  await page.getByTestId("onboarding-skip").click()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)
  await expect(hint(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)
})

test("the welcome offers the language first, and the rest of it follows the choice", async ({
  page,
}) => {
  await loginFresh(page)
  const welcome = page.getByTestId("onboarding-dialog")
  await expect(page.getByTestId("onboarding-language")).toBeVisible()
  await expect(welcome).toContainText("Pick a language")

  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().endsWith("/users/me/preferences")
  )
  // A choice in one row: an option's name carries its second line, so it is
  // matched by its start.
  await page.getByTestId("onboarding-language").click()
  await page.getByRole("option", { name: /^Русский/ }).click()
  await saved
  // The account keeps it (D224), and the welcome is read in it at once.
  await expect(welcome).toContainText("Выберите язык")

  // Back to the browser's language, so every other scenario reads English.
  await page.getByTestId("onboarding-language").click()
  await page.getByRole("option", { name: /^Язык браузера/ }).click()
  await expect(welcome).toContainText("Pick a language")
  await page.getByTestId("onboarding-skip").click()
  await expect(welcome).toHaveCount(0)
})

test("the tour is taken by hand, from a new SQLite database to its file deleted", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000)
  const folder = `e2e-tour-folder-${Date.now()}`
  await loginFresh(page)
  await page.getByTestId("onboarding-primary").click()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)

  // 1. A database made here: + → SQLite → Create here → Make.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 1 of 10")
  await expectRingOn(page, "add-connector")
  await page.screenshot({ path: testInfo.outputPath("1-add.png") })
  await page.getByTestId("add-connector").click()
  await expectRingOn(page, "adapter-sqlite")
  await page.getByTestId("adapter-sqlite").click()
  await expectRingOn(page, "make-here")
  await page.getByTestId("make-here").click()
  await expectRingOn(page, "make-here-submit")
  await page.screenshot({ path: testInfo.outputPath("1-make.png") })
  const made = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/connectors/made-here")
  )
  await page.getByTestId("make-here-submit").click()
  const connector = (await (await made).json()) as { name: string; config: { path: string } }
  // A numbered name when an earlier run left `dataplayer.db` behind (D263).
  const file = connector.config.path.split("/").pop() ?? ""

  // 2. Its table.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 2 of 10")
  await expectRingOn(page, "catalog-node-tasks")
  await page.getByTestId("catalog-node-tasks").click()

  // 3. Filtered: the chapter ends when the count is on the button.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 3 of 10")
  await expectRingOn(page, "grid-filter")
  await page.screenshot({ path: testInfo.outputPath("3-filter.png") })
  await addFilter(page, "status", "equals", "blocked")

  // 4. A cell changed.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 4 of 10")
  await expectRingOn(page, "grid-cell-0-title")
  await page.getByTestId("grid-cell-0-title").dblclick()
  await expectRingOn(page, "grid-cell-editor")
  await page.getByTestId("grid-edit-value").fill("Changed during the tour")
  await page.getByTestId("grid-edit-save").click()

  // 5. The table as a query, run.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 5 of 10")
  await expectRingOn(page, "grid-query")
  await page.getByTestId("grid-query").click()
  await expectRingOn(page, "query-run")
  await page.screenshot({ path: testInfo.outputPath("5-run.png") })
  await page.getByTestId("query-run").click()

  // 6. The connection deleted; its file stays.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 6 of 10")
  await expectRingOn(page, `connector-edit-${connector.name}`)
  await page.getByTestId(`connector-edit-${connector.name}`).click()
  await page.locator('[data-testid="delete-connector"][tabindex="0"]').click()
  await expectRingOn(page, "confirm-accept")
  await page.screenshot({ path: testInfo.outputPath("6-confirm.png") })
  await page.getByTestId("confirm-accept").click()

  // 7. A connection to the person's own storage.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 7 of 10")
  await page.getByTestId("add-connector").click()
  await expectRingOn(page, "adapter-file")
  await page.getByTestId("adapter-file").click()
  await expectRingOn(page, "create-from-catalog")
  await page.getByTestId("create-from-catalog").click()
  await expectRingOn(page, "save-connector")
  await page.getByTestId("connector-name").fill(folder)
  await page.getByTestId("save-connector").click()

  // 8. The database file found in it.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 8 of 10")
  await page.getByTestId(`connector-${folder}`).click()
  await expectRingOn(page, "catalog-node-databases")
  await page.getByTestId("catalog-node-databases").click()

  // 9. And deleted, from the actions of the catalog.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 9 of 10")
  await expectRingOn(page, `catalog-check-${file}`)
  await page.getByTestId(`catalog-check-${file}`).click()
  await expectRingOn(page, "catalog-actions")
  await page.getByTestId("catalog-actions").click()
  await page.getByTestId("menu-item-delete").click()
  await expectRingOn(page, "action-submit")
  await page.getByTestId("action-submit").click()

  // 10. A server shown that could be started here. The last chapter offers
  // Finish and the list of tours, and pressing the start button itself ends
  // the tour rather than sending the hint back to the chapter's first step.
  await expect(page.getByTestId("tour-position")).toHaveText("Step 10 of 10")
  await expect(page.getByTestId("tour-end")).toHaveCount(0)
  await expect(page.getByTestId("tour-more")).toHaveText("See more tours")
  await page.getByTestId("add-connector").click()
  await expectRingOn(page, "adapter-redis")
  await page.getByTestId("adapter-redis").click()
  await expectRingOn(page, "start-service-redis")
  await expect(page.getByTestId("tour-next")).toHaveText("Finish")
  await page.screenshot({ path: testInfo.outputPath("10-service.png") })
  await page.getByTestId("start-service-redis").click()
  await expect(hint(page)).toHaveCount(0)
  const start = page.getByRole("dialog").filter({ has: page.getByTestId("start-service-dialog") })
  await start.getByRole("button", { name: "Cancel", exact: true }).click()
  await expect(page.getByTestId("start-service-dialog")).toHaveCount(0)
  await expect(hint(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)

  await deleteConnector(page, folder)
})

test("the tour can be ended, and Preferences starts it again from its first chapter", async ({
  page,
}) => {
  await loginFresh(page)
  await page.getByTestId("onboarding-primary").click()
  await expect(page.getByTestId("tour-position")).toHaveText("Step 1 of 10")
  // The question is a window under the tour's layer: the dim steps aside for
  // it, and comes back when the tour goes on.
  await page.getByTestId("tour-end").click()
  await expect(page.getByTestId("confirm-accept")).toBeVisible()
  await expect(page.getByTestId("tour-ring")).toHaveCount(0)
  await expect(hint(page)).toHaveCount(0)
  await page.screenshot({ path: test.info().outputPath("end-question.png") })
  await page.getByTestId("confirm-cancel").click()
  await expect(page.getByTestId("tour-ring")).toBeVisible()
  await page.getByTestId("tour-end").click()
  await page.getByTestId("confirm-accept").click()
  await expect(hint(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("onboarding-dialog")).toHaveCount(0)

  await page.goto("/preferences/tours")
  await page.getByTestId("preference-tour-basics").click()
  await page.waitForURL("/")
  await expect(page.getByTestId("tour-position")).toHaveText("Step 1 of 10")
  await expectRingOn(page, "add-connector")
  await page.getByTestId("tour-end").click()
  await page.getByTestId("confirm-accept").click()
  await expect(hint(page)).toHaveCount(0)
})
