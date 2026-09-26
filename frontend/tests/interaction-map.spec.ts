import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createFileConnector, createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector } from "./utils/workspace"

/**
 * The map of what the connections can give each other (D174), opened from the
 * rail like Dashboards and AI, and a pair opened from one of its arrows.
 */

/** A connection's id, read off the node the map drew for it. */
async function nodeId(page: Page, name: string): Promise<string> {
  const node = page.locator('[data-testid^="graph-node-"]', { hasText: name })
  await expect(node).toHaveCount(1)
  const testId = await node.getAttribute("data-testid")
  return (testId ?? "").replace("graph-node-", "")
}

test("maps what two connections give each other and opens a pair from an arrow", async ({
  page,
}) => {
  const database = `e2e-map-db-${Date.now()}`
  const files = `e2e-map-files-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, database)
  await createFileConnector(page, files)

  await page.getByTestId("space-map").click()
  await expect(page.getByTestId("space-map")).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("interaction-map")).toBeVisible()
  // No first panel here, so nothing to hide.
  await expect(page.getByTestId("app-toggle-first-panel")).toHaveCount(0)
  const databaseId = await nodeId(page, database)
  const filesId = await nodeId(page, files)

  // One arrow a direction, named by what it does.
  const saving = page.getByTestId(`graph-edge-${databaseId}>${filesId}`)
  await expect(saving).toHaveAttribute("aria-label", "Save as CSV")
  await expect(page.getByTestId(`graph-edge-${filesId}>${databaseId}`)).toHaveAttribute(
    "aria-label",
    "Create a table · Add rows to a table"
  )
  await page.getByTestId(`graph-node-${databaseId}`).click()
  await page.screenshot({ path: "test-results/interaction-map-node.png" })
  await saving.press("Enter")
  const inspector = page.getByTestId("graph-inspector")
  await expect(inspector).toContainText("Open to you")
  await page.screenshot({ path: "test-results/interaction-map.png" })

  // The pair it opens is in Data, the source on the left.
  await page.getByTestId("interaction-map-open-pair").click()
  await expect(page.getByTestId("space-data")).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("pair-window")).toBeVisible()
  await expect(page.getByTestId("pair-side-left").getByTestId("catalog-list")).toBeVisible()
  await expect(page.getByTestId("pair-side-right")).toContainText("reports")

  await page.locator('[data-testid^="window-close-pair:"]').click()
  await expect(page.getByTestId("pair-window")).toHaveCount(0)
  await deleteConnector(page, files)
  await deleteConnector(page, database)
})
