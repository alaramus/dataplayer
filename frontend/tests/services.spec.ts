import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { connectorRow } from "./utils/workspace"

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
// Typed rather than left to the server, because that is the half of the form
// with a consequence: what the server makes up is said once and then never
// again, and this scenario looks at both halves of that.
const SERVICE_PASSWORD = "e2e-chosen-9"

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
  const start = page.getByTestId("start-service-postgres")
  await expect(start).toBeEnabled()
  await start.click()

  // Two ways to ask, and this scenario takes the one with questions in it: a
  // run has to name its own connection, and the automatic path names it after
  // the template (D88).
  await expect(page.getByTestId("start-service-dialog")).toBeVisible()
  await page.getByTestId("service-mode").click()
  await page.getByRole("option", { name: "Let me choose" }).click()
  await page.getByTestId("service-name").fill(SERVICE_NAME)
  // A password of its own, which is the reason the form asks for one: what
  // this server makes up is said once and then gone.
  await page.getByTestId("service-password").fill(SERVICE_PASSWORD)
  // Nothing to look at: this scenario is about the lifecycle, and filling a
  // database is minutes it does not need. The port stays at zero, so the
  // runtime picks one.
  await page.getByTestId("service-sample-data").click()
  await page.getByTestId("start-service-confirm").click()

  // The catalog closes and the work is watched from the bar at the foot of the
  // screen: a step the server named, never a percentage this side invented
  // (D81). The panel at the foot of the screen is where the services are, and
  // the button is where they are said to exist (D69, D143).
  const openServices = page.getByTestId("command-services")
  await openServices.click()
  const services = page.getByTestId("managed-services")
  await expect(services).toBeVisible()

  // And then it is an ordinary connection, made by nobody's browser (D83).
  await expect(connectorRow(page, SERVICE_NAME)).toBeVisible({ timeout: 90_000 })
  await expect(services).toContainText("running")

  // Where it listens opens by itself once it is ready, whichever way it was
  // asked for: the port is the runtime's answer and the host is not the one
  // the connection holds, so neither is something anybody was told (D89).
  const details = page.getByTestId("service-credentials-dialog")
  await expect(details).toBeVisible({ timeout: 90_000 })
  await expect(details.getByTestId("credential-host")).toContainText("127.0.0.1")
  // And this is the one moment the password is said out loud — in the row and
  // in the line most tools take, which is the one worth keeping.
  await expect(details.getByTestId("credential-password")).toContainText(
    SERVICE_PASSWORD
  )
  await expect(details.getByTestId("credential-url")).toContainText(
    SERVICE_PASSWORD
  )
  await page.getByTestId("credentials-done").click()

  // Opening it reads the catalog of the database that was just made. The panel
  // is put away first, from its own head, to be asked for again below.
  await page.getByTestId("bottom-panel-hide").click()
  await expect(services).toHaveCount(0)
  await connectorRow(page, SERVICE_NAME).click()
  await expect(page.getByTestId("catalog-list")).toContainText("System")

  // The same list again, as often as it is asked — and without the password
  // this time: an address is not a secret, and that is what makes it something
  // a person can be told twice (D89).
  await openServices.click()
  const row = services
    .locator('[data-testid^="managed-service-"]')
    .filter({ hasText: SERVICE_NAME })
  await row.locator('[data-testid^="credentials-service-"]').click()
  await expect(details.getByTestId("credential-host")).toContainText("127.0.0.1")
  await expect(details.getByTestId("credential-password")).toHaveCount(0)
  await expect(details).not.toContainText(SERVICE_PASSWORD)
  await expect(details.getByTestId("credential-url")).toBeVisible()
  await page.getByTestId("credentials-done").click()

  // Stopped and started again from its row, keeping the connection: the
  // offer follows the container, so each press turns the button over.
  await row.locator('[data-testid^="stop-service-"]').click()
  await expect(row.locator('[data-testid^="start-service-"]')).toBeVisible({
    timeout: 30_000,
  })
  await expect(row).toContainText("stopped")
  await row.locator('[data-testid^="start-service-"]').click()
  await expect(row.locator('[data-testid^="stop-service-"]')).toBeVisible({
    timeout: 30_000,
  })
  await expect(row).toContainText("running")
  await expect(connectorRow(page, SERVICE_NAME)).toBeVisible()

  // Removing the service takes the container and its data, and the connection
  // it made when that is ticked as well — which it is by default, because a
  // connection to a database that no longer exists works for nobody.
  await row.locator('[data-testid^="remove-service-"]').click()
  await expect(page.getByTestId("confirm-also")).toBeVisible()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0, { timeout: 60_000 })

  await expect(connectorRow(page, SERVICE_NAME)).toHaveCount(0)
})

test("starts an SSH server with sample files in its home and opens them", async ({
  page,
}) => {
  test.setTimeout(150_000)
  const name = `e2e-ssh-service-${Date.now()}`
  await login(page)
  await page.getByTestId("add-connector").click()
  await expect(page.getByTestId("adapter-catalog")).toBeVisible()
  await page.getByTestId("adapter-ssh").click()

  await page.getByTestId("start-service-ssh").click()
  await page.getByTestId("service-mode").click()
  await page.getByRole("option", { name: "Let me choose" }).click()
  await page.getByTestId("service-name").fill(name)
  // Sample data stays ticked: the home is filled with a file of every kind.
  await page.getByTestId("start-service-confirm").click()

  // Ready means it answered to a password, over the key it presented first
  // (D153), and the window says where it listens as the line ssh takes.
  const details = page.getByTestId("service-credentials-dialog")
  await expect(details).toBeVisible({ timeout: 120_000 })
  await expect(details.getByTestId("credential-url")).toContainText(
    "ssh://dataplayer@127.0.0.1:"
  )
  await expect(details.getByTestId("credential-password")).toBeVisible()
  await page.getByTestId("credentials-done").click()

  await connectorRow(page, name).click()
  await expect(page.getByTestId("catalog-list")).toContainText("sample.csv")
  await page.getByTestId("catalog-node-sample.csv").click()
  await expect(page.getByTestId("row-grid")).toContainText("city-1")

  // A recording and a PDF are read on the server by range, never copied here
  // first (D152): the header gives the picture size, and the player loads.
  await page.getByTestId("catalog-node-clip.mp4").click()
  await expect(page.getByTestId("media-details")).toContainText("160 × 120")
  const video = page.getByTestId("media-player")
  await expect
    .poll(async () => video.evaluate((element: HTMLMediaElement) => element.readyState))
    .toBeGreaterThan(0)
  await page.getByTestId("catalog-node-guide.pdf").click()
  await expect(page.getByTestId("pdf-page-1").locator("canvas")).toBeVisible()

  await page.getByTestId("command-services").click()
  const row = page
    .getByTestId("managed-services")
    .locator('[data-testid^="managed-service-"]')
    .filter({ hasText: name })
  await row.locator('[data-testid^="remove-service-"]').click()
  await page.getByTestId("confirm-accept").click()
  await expect(row).toHaveCount(0, { timeout: 60_000 })
  await expect(connectorRow(page, name)).toHaveCount(0)
})
