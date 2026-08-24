import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, editConnector } from "./utils/workspace"

/**
 * The dot beside a connection, and what switching one off does.
 *
 * In the browser rather than in a unit test because the whole point is what
 * arrives without being asked for: a socket, a monitor on the server and a
 * store on this side all have to line up before the colour changes, and none
 * of them proves the others.
 */

// The server probes every fifteen seconds, and these scenarios wait for two
// or three rounds. The default budget of thirty seconds is for the whole test,
// not for one assertion, so it runs out while the dot is still right.
test.describe.configure({ timeout: 120_000 })

function stateDot(page: import("@playwright/test").Page, name: string) {
  return page.getByTestId(`connector-state-${name}`)
}

test("a working connection turns green on its own", async ({ page }) => {
  const name = `e2e-health-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  // Nothing is pressed here. The screen subscribed when it opened, and the
  // server probes because somebody is watching.
  await expect(stateDot(page, name)).toHaveAttribute("data-state", "ok", {
    timeout: 30_000,
  })

  await deleteConnector(page, name)
})

test("a connection switched off goes yellow and will not open", async ({ page }) => {
  const name = `e2e-off-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)
  await expect(stateDot(page, name)).toHaveAttribute("data-state", "ok", {
    timeout: 30_000,
  })

  await editConnector(page, name)
  await page.getByTestId("connector-enabled").click()
  await page.getByTestId("save-connector").click()

  await expect(stateDot(page, name)).toHaveAttribute("data-state", "disabled")

  // Still listed and still reachable for editing — switching off is not
  // deleting — but pressing it no longer loads a catalog.
  await connectorRow(page, name).click()
  await expect(page.locator('[data-testid^="workspace-tab-catalog:"]')).toHaveCount(0)

  // And back on again, which is the whole difference from deleting it.
  await editConnector(page, name)
  await page.getByTestId("connector-enabled").click()
  await page.getByTestId("save-connector").click()
  await expect(stateDot(page, name)).toHaveAttribute("data-state", "ok", {
    timeout: 30_000,
  })

  await deleteConnector(page, name)
})
