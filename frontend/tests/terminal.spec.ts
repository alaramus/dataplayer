import { expect, test } from "@playwright/test"

import { createSshConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

/**
 * A terminal on an SSH connection, opened from the rail (D143, D149).
 *
 * Against `sshd` from compose.override.yml. The shell does the arithmetic, so
 * what is looked for on the screen is its answer, never the echo of what was
 * typed.
 */
test("the Terminals button opens a shell on the connection being worked in", async ({ page }) => {
  const name = `e2e-terminal-${Date.now()}`
  await login(page)
  await createSshConnector(page, name)
  const panel = page.getByTestId("bottom-panel")
  const screen = page.getByTestId("terminal-screen")

  // Outside a connection the panel offers the ones that have a shell.
  await page.getByTestId("command-terminals").click()
  await expect(panel).toHaveAttribute("aria-label", "Terminals")
  await expect(page.getByTestId(`terminal-open-${name}`)).toBeVisible()
  await page.getByTestId("command-terminals").click()
  await expect(panel).toHaveCount(0)

  // Inside one, the button goes straight to a terminal on it.
  await openConnector(page, name)
  await page.getByTestId("command-terminals").click()
  await expect(page.locator('[data-testid^="terminal-tab-"]')).toContainText(name)
  await screen.click()
  await page.keyboard.type('echo "dp-$((6*7))"')
  await page.keyboard.press("Enter")
  await expect(screen).toContainText("dp-42")

  // Another tool shown in the panel and this one again: the same shell.
  await page.getByTestId("command-services").click()
  await expect(panel).toHaveAttribute("aria-label", "Services")
  await page.getByTestId("command-terminals").click()
  await expect(screen).toContainText("dp-42")

  await screen.click()
  await page.keyboard.type("exit 5")
  await page.keyboard.press("Enter")
  await expect(page.getByTestId("terminal-notice")).toContainText("status 5")
  await page.getByTestId("terminal-open-again").click()
  await expect(page.getByTestId("terminal-notice")).toHaveCount(0)

  await page.locator('[data-testid^="terminal-close-"]').click()
  await expect(page.locator('[data-testid^="terminal-tab-"]')).toHaveCount(0)

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
