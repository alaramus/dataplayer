import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"
import { toast } from "./utils/notices"

test("shows the structure of a relation beside its rows", async ({ page }) => {
  const name = `e2e-structure-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")

  await openNode(page, "app_users")
  const structure = page.getByTestId("grid-structure")
  await structure.hover()
  await expect(page.locator(".app-tooltip")).toHaveText("Structure")
  await structure.click()

  const view = page.getByTestId("structure-view")
  await expect(view).toBeVisible()
  // The tooltip goes with the tab it was on. The pointer never left the
  // button — the button left the screen — so no mouseleave is raised and
  // nothing else takes it off; it used to hang over the tab that just opened.
  await expect(page.locator(".app-tooltip")).toHaveCount(0)
  await expect(view).toContainText("user_id")
  await expect(view).toContainText("bigint")
  await expect(view.getByTestId("structure-badge-primary_key").first()).toBeVisible()
  await expect(view.getByTestId("structure-fk").first()).toContainText(
    "demo_lab.organizations"
  )

  await page.locator('[data-testid^="workspace-tab-rows:"]').first().click()
  await expect(page.getByTestId("row-grid")).toBeVisible()

  // Put the inactive structure tab in a section of its own, leaving rows in
  // the work section that new panels target.
  const structureTab = page.locator('[data-testid^="workspace-tab-structure:"]').first()
  const work = page.getByTestId("workspace-leaf-work")
  const from = await structureTab.boundingBox()
  const onto = await work.boundingBox()
  if (from === null || onto === null) throw new Error("the structure tab has no box")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width * 0.1, onto.y + onto.height * 0.6, { steps: 12 })
  await page.mouse.up()

  await expect(view).toBeVisible()
  await expect(page.getByTestId("row-grid")).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})

test("adds and drops a PostgreSQL column", async ({ page }) => {
  const name = `e2e-columns-${Date.now()}`
  const column = `review_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  await view.getByTestId("structure-add-column").click()
  await page.getByTestId("structure-add-name").fill(column)
  await page.getByTestId("structure-add-save").click()
  await expect(view).toContainText(column)

  await view.getByTestId(`structure-drop-${column}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(view.getByTestId(`structure-drop-${column}`)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("renames a PostgreSQL column", async ({ page }) => {
  const name = `e2e-rename-${Date.now()}`
  const original = `before_${Date.now()}`
  const renamed = `after_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await page.getByTestId("catalog-node-tags").click()
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  await view.getByTestId("structure-add-column").click()
  await page.getByTestId("structure-add-name").fill(original)
  await page.getByTestId("structure-add-save").click()
  await expect(view).toContainText(original)

  await view.getByTestId(`structure-rename-${original}`).click()
  await page.getByTestId("structure-rename-new-name").fill(renamed)
  await page.getByTestId("structure-rename-save").click()
  await expect(view.getByTestId(`structure-rename-${renamed}`)).toBeVisible()
  await expect(view.getByTestId(`structure-rename-${original}`)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("stops requiring a value in a column and requires it again", async ({ page }) => {
  const name = `e2e-nullability-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  const cell = view.getByTestId("structure-nullability-label")
  await expect(cell).toHaveText("no")

  await cell.click()
  await page.getByTestId("structure-nullability-save").click()
  await expect(cell).toHaveText("yes")

  await cell.click()
  await page.getByTestId("structure-nullability-save").click()
  await expect(cell).toHaveText("no")

  await deleteConnector(page, name)
})

test("counts the rows in the way instead of failing to require a value", async ({ page }) => {
  const name = `e2e-nullability-blocked-${Date.now()}`
  const column = `needs_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  await view.getByTestId("structure-add-column").click()
  await page.getByTestId("structure-add-name").fill(column)
  await page.getByTestId("structure-add-save").click()
  await expect(view).toContainText(column)

  // Every existing row of tags is empty in a column added a moment ago, so
  // this is the answer the feature exists for.
  await view.getByTestId(`structure-nullability-${column}`).click()
  await page.getByTestId("structure-nullability-save").click()
  await expect(page.getByTestId("structure-nullability-blocked")).toContainText(
    new RegExp(String.raw`\d+ rows? ha(?:ve|s) no value in ${column}`)
  )
  await expect(view.getByTestId(`structure-nullability-${column}`)).toHaveText("yes")

  await page.getByRole("button", { name: "Cancel" }).click()
  await view.getByTestId(`structure-drop-${column}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(view.getByTestId(`structure-drop-${column}`)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("changes a column type and counts the values in the way", async ({ page }) => {
  const name = `e2e-type-${Date.now()}`
  const column = `score_${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "tags")
  await page.getByTestId("grid-structure").click()

  // A column full of words, asked to become a number: the source counts what
  // it cannot read and rewrites nothing.
  const view = page.getByTestId("structure-view")
  await view.getByTestId("structure-type-label").click()
  await page.getByTestId("structure-type-select").click()
  await page.getByRole("option", { name: /^Integer/ }).click()
  await page.getByTestId("structure-type-save").click()
  await expect(page.getByTestId("structure-type-blocked")).toContainText(
    String.raw`rows hold a value the chosen type cannot read`
  )
  await page.getByRole("button", { name: "Cancel" }).click()
  await expect(view.getByTestId("structure-type-label")).toHaveText(
    "character varying(40)"
  )

  // The same conversion on a column added a moment ago, which every row is
  // empty in, goes through.
  await view.getByTestId("structure-add-column").click()
  await page.getByTestId("structure-add-name").fill(column)
  await page.getByTestId("structure-add-save").click()
  await expect(view.getByTestId(`structure-type-${column}`)).toHaveText("text")

  await view.getByTestId(`structure-type-${column}`).click()
  await page.getByTestId("structure-type-select").click()
  await page.getByRole("option", { name: /^Integer/ }).click()
  await page.getByTestId("structure-type-save").click()
  await expect(view.getByTestId(`structure-type-${column}`)).toHaveText("integer")

  await view.getByTestId(`structure-drop-${column}`).click()
  await page.getByTestId("confirm-accept").click()
  await expect(view.getByTestId(`structure-drop-${column}`)).toHaveCount(0)

  await deleteConnector(page, name)
})

test("indexes a column, refuses a unique one that repeats, and drops it again", async ({
  page,
}) => {
  const name = `e2e-index-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "app_users")
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  // The name is the source's to choose, so the test does not predict it: it
  // takes the row that appeared. Predicting it would also make the test depend
  // on what earlier runs left behind, since PostgreSQL suffixes a taken name.
  const rowIds = () =>
    view
      .locator('[data-testid^="structure-index-row-"]')
      .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-testid") ?? ""))

  // One organisation owns more than one user, so a unique index cannot be
  // built and the source says how many values repeat.
  await view.getByTestId("structure-add-index").click()
  await page.getByTestId("structure-index-columns").click()
  await page.getByRole("option", { name: "organization_id" }).click()
  await page.keyboard.press("Escape")
  await page.getByTestId("structure-index-unique").click()
  await page.getByTestId("structure-index-save").click()
  await expect(page.getByTestId("structure-index-blocked")).toContainText(
    "appear more than once"
  )

  // The same columns without uniqueness go through, under a name the source
  // chose: nothing was typed for it.
  const before = await rowIds()
  await page.getByTestId("structure-index-unique").click()
  await page.getByTestId("structure-index-save").click()
  await expect.poll(async () => (await rowIds()).length).toBe(before.length + 1)

  const added = (await rowIds()).find((id) => !before.includes(id)) ?? ""
  const row = view.locator(`[data-testid="${added}"]`)
  await expect(row).toContainText("(organization_id)")
  await expect(row).toContainText("btree")

  await row.getByRole("button").click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0)

  // An index a constraint stands on is named, not relayed as a driver error.
  await view.getByTestId("structure-drop-index-app_users_organization_id_email_key").click()
  await page.getByTestId("confirm-accept").click()
  await expect(
    toast(page, "app_users_organization_id_email_key")
  ).toBeVisible()

  await deleteConnector(page, name)
})

test("promises uniqueness, refuses what repeats, and points at another table", async ({
  page,
}) => {
  const name = `e2e-constraint-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "demo_lab")
  await openNode(page, "app_users")
  await page.getByTestId("grid-structure").click()

  const view = page.getByTestId("structure-view")
  const named = () => view.locator("[data-constraint]").evaluateAll(
    (rows) => rows.map((row) => row.getAttribute("data-constraint") ?? "")
  )

  // One organisation owns more than one user, so uniqueness cannot be
  // promised and the source says how many values repeat.
  await view.getByTestId("structure-add-constraint").click()
  await page.getByTestId("structure-constraint-columns").click()
  await page.getByRole("option", { name: "organization_id" }).click()
  await page.keyboard.press("Escape")
  await page.getByTestId("structure-constraint-save").click()
  await expect(page.getByTestId("structure-constraint-blocked")).toContainText(
    "appear more than once"
  )

  // The same columns as a foreign key: the target says which of its keys may
  // be pointed at, and nothing here composes an id or a predicate.
  const before = await named()
  await page.getByTestId("structure-constraint-kind").click()
  await page.getByRole("option", { name: "Foreign key" }).click()
  await page.getByTestId("structure-constraint-target").click()
  await page.getByRole("option", { name: "organizations", exact: true }).click()
  await expect(page.getByTestId("structure-constraint-key")).toBeVisible()
  await page.getByTestId("structure-constraint-save").click()
  await expect.poll(async () => (await named()).length).toBe(before.length + 1)

  const added = (await named()).find((item) => !before.includes(item)) ?? ""
  const row = view.locator(`[data-constraint="${added}"]`)
  await expect(row).toContainText("demo_lab.organizations")

  await row.getByRole("button").click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0)

  await deleteConnector(page, name)
})
