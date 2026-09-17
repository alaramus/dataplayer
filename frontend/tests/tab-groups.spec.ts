import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector, rowsTabs } from "./utils/workspace"

/** The saved groups stand behind the one list button on a tool rail. */
async function openGroups(page: Page) {
  await page.getByTestId("open-tab-groups").click()
  await expect(page.getByRole("menu", { name: "Saved tab groups", exact: true })).toBeVisible()
}

async function closeGroups(page: Page) {
  await page.keyboard.press("Escape")
  await expect(page.getByRole("menu", { name: "Saved tab groups", exact: true })).toHaveCount(0)
}

async function saveGroup(page: Page, name: string, offered?: string) {
  await page.getByTestId("save-tab-group").click()
  // What the dialog opens on, when the caller cares: a name nobody has to
  // think of, and one Save accepts as it stands.
  if (offered !== undefined) await expect(page.getByTestId("tab-group-name")).toHaveValue(offered)
  await page.getByTestId("tab-group-name").fill(name)
  await page.getByTestId("confirm-tab-group-name").click()
  await openGroups(page)
  await expect(page.getByRole("button", { name: `Open group ${name}`, exact: true })).toBeVisible()
  await closeGroups(page)
}

/** Opening a group closes the list, so every opening starts by opening it. */
async function openGroup(page: Page, name: string) {
  await openGroups(page)
  await page.getByRole("button", { name: `Open group ${name}`, exact: true }).click()
}

async function manageGroup(page: Page, name: string, action: string) {
  await openGroups(page)
  await page.getByRole("button", { name: `Manage group ${name}`, exact: true }).click()
  await page.getByTestId(`menu-item-${action}`).click()
}

test("saves column layouts, replaces tabs, remembers the warning and manages multiple groups", async ({ page }) => {
  // Around eighty steps of one journey: the groups, the warning and the
  // renaming only mean anything on state the steps before them left. It ran
  // out of the default thirty seconds around the last of them, and which step
  // was reported then depended on where the clock stopped.
  test.setTimeout(90_000)
  const connection = `e2e-groups-${Date.now()}`
  await login(page)

  // The list button always stands; with nothing saved yet it says so.
  await openGroups(page)
  await expect(page.getByRole("menu", { name: "Saved tab groups", exact: true })).toContainText(
    "No saved groups yet"
  )
  await closeGroups(page)

  await createPostgresConnector(page, connection)
  await openConnector(page, connection)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")
  await openNode(page, "pg_namespace")
  const namespaceTab = rowsTabs(page).filter({ hasText: "pg_namespace" })
  const classTab = rowsTabs(page).filter({ hasText: "pg_class" })
  const main = page.getByTestId("workspace-leaf-work")
  const from = await namespaceTab.boundingBox()
  const onto = await main.boundingBox()
  if (from === null || onto === null) throw new Error("The tab or column has no rectangle")
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(onto.x + onto.width * 0.1, onto.y + onto.height * 0.6, { steps: 12 })
  await page.mouse.up()
  const columns = page.locator('[data-testid^="workspace-leaf-"]')
  await expect(columns).toHaveCount(4)
  const widths = await columns.evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width))
  await saveGroup(page, "Catalog tables", "new group")

  await namespaceTab.locator('[data-testid^="workspace-close-"]').click()
  await classTab.locator('[data-testid^="workspace-close-"]').click()
  await openNode(page, "pg_type")
  await saveGroup(page, "Types")
  await openGroups(page)
  await expect(page.getByTestId("open-tab-group")).toHaveCount(2)
  await closeGroups(page)
  const warning = page.getByRole("dialog", { name: "Replace current tabs?", exact: true })

  await openGroup(page, "Catalog tables")
  await expect(warning).toContainText("Tabs outside the group will disappear.")
  await warning.getByTestId("confirm-remember").click()
  await warning.getByTestId("confirm-cancel").click()
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(rowsTabs(page)).toContainText("pg_type")
  await openGroup(page, "Catalog tables")
  await expect(warning).toBeVisible()
  await warning.getByRole("button", { name: "Close window", exact: true }).click()
  await expect(rowsTabs(page)).toContainText("pg_type")

  await openGroup(page, "Catalog tables")
  await warning.getByTestId("confirm-remember").click()
  await warning.getByTestId("confirm-accept").click()
  await expect(columns).toHaveCount(4)
  await expect(namespaceTab).toBeVisible()
  await expect(classTab).toBeVisible()
  const restoredWidths = await columns.evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width))
  restoredWidths.forEach((width, index) => expect(Math.abs(width - widths[index]!)).toBeLessThan(3))

  await openGroup(page, "Types")
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(rowsTabs(page)).toContainText("pg_type")
  await expect(warning).toHaveCount(0)
  await page.reload()
  await openGroups(page)
  await expect(page.getByTestId("open-tab-group")).toHaveCount(2)
  await closeGroups(page)
  await openGroup(page, "Catalog tables")
  await expect(namespaceTab).toBeVisible()
  await expect(warning).toHaveCount(0)

  await manageGroup(page, "Catalog tables", "rename-group")
  await page.getByTestId("tab-group-name").fill("Reference tables")
  await page.getByTestId("confirm-tab-group-name").click()
  await namespaceTab.locator('[data-testid^="workspace-close-"]').click()
  await manageGroup(page, "Reference tables", "update-group")
  await openGroup(page, "Types")
  await expect(rowsTabs(page)).toContainText("pg_type")
  await openGroup(page, "Reference tables")
  await expect(rowsTabs(page)).toHaveCount(1)
  await expect(classTab).toBeVisible()

  for (const name of ["Reference tables", "Types"]) {
    await manageGroup(page, name, "delete-group")
    await page.getByTestId("confirm-accept").click()
    await openGroups(page)
    await expect(page.getByRole("button", { name: `Open group ${name}`, exact: true })).toHaveCount(0)
    await closeGroups(page)
  }
  // Emptied, the list says so again rather than vanishing.
  await openGroups(page)
  await expect(page.getByRole("menu", { name: "Saved tab groups", exact: true })).toContainText(
    "No saved groups yet"
  )
  await closeGroups(page)
  await expect(classTab).toBeVisible()
  await deleteConnector(page, connection)
})
