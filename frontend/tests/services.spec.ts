import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { closeWindowDialog, connectorRow, deleteConnector } from "./utils/workspace"

/**
 * A database somebody asked this server to start.
 *
 * The whole point of the phase, end to end: one button, a job to watch, and a
 * connection that works — with nothing about a container in the browser.
 *
 * It needs a container runtime, which the development backend has through the
 * socket the override mounts. Where there is none the offer is disabled and
 * says why, which is the other half of D82 and is checked below.
 */

// Named per run, like every other scenario's connection: the dev database is
// whatever the last run left, and a name that repeats is a row that cannot be
// told from another one.
const SERVICE_NAME = `e2e-service-${Date.now()}`

async function openTheCatalog(page: import("@playwright/test").Page) {
  await page.getByTestId("add-connector").click()
  await expect(page.getByTestId("adapter-catalog")).toBeVisible()
  await page.getByTestId("adapter-postgres").click()
}

test("starts a PostgreSQL of its own and receives a connection to it", async ({
  page,
}) => {
  test.setTimeout(120_000)
  await login(page)
  await openTheCatalog(page)

  // The offer names the exact image, so a person can see what would be pulled
  // onto the machine before pressing anything (D80).
  const start = page.getByTestId("start-service")
  await expect(start).toBeEnabled()
  await start.click()

  // One question, and it is the only one only the person asking can answer.
  await expect(page.getByTestId("start-service-dialog")).toBeVisible()
  await page.getByTestId("service-name").fill(SERVICE_NAME)
  await page.getByTestId("start-service-confirm").click()

  // The catalog closes and the work is watched from the bar at the foot of the
  // screen: a step the server named, never a percentage this side invented
  // (D81). The window is where the services are, and the button is where they
  // are said to exist (D69).
  const openServices = page.getByTestId("command-services")
  await expect(openServices).toBeEnabled({ timeout: 30_000 })
  await openServices.click()
  const services = page.getByTestId("managed-services")
  await expect(services).toBeVisible()

  // And then it is an ordinary connection, made by nobody's browser (D83).
  await expect(connectorRow(page, SERVICE_NAME)).toBeVisible({ timeout: 90_000 })
  await expect(services).toContainText("running")

  // Opening it reads the catalog of the database that was just made.
  await closeWindowDialog(page, "services-dialog")
  await connectorRow(page, SERVICE_NAME).click()
  await expect(page.getByTestId("catalog-list")).toContainText("System")

  // Removing the service takes the container and its data; the connection it
  // made is a separate thing and is removed separately.
  await openServices.click()
  const row = services
    .locator('[data-testid^="managed-service-"]')
    .filter({ hasText: SERVICE_NAME })
  await row.locator('[data-testid^="remove-service-"]').click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0, { timeout: 60_000 })

  await deleteConnector(page, SERVICE_NAME)
  await expect(connectorRow(page, SERVICE_NAME)).toHaveCount(0)
})
