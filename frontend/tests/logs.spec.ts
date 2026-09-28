import { expect, test } from "@playwright/test"

import { login } from "./utils/login"
import { colleagueEmail, COLLEAGUE_PASSWORD, createColleague, removeColleague, signInAs, signOut } from "./utils/people"
import { chooseTheme } from "./utils/theme"

/**
 * The server's log in the panel at the foot of the screen (D184): what the
 * backend and the metrics collector wrote, for a superuser.
 */

test("a superuser reads the server's log, narrowed by level and by words", async ({ page }) => {
  await login(page)
  await page.getByTestId("command-logs").click()
  const tool = page.getByTestId("logs-tool")
  await expect(tool).toBeVisible()

  // The requests this page has just made are in it, and Docker's health
  // check, asked every ten seconds, is not.
  const body = page.getByTestId("logs-body")
  await expect(body).toContainText("/api/v1/users/me")
  await expect(body).not.toContainText("health-check")

  await page.getByTestId("logs-search").fill("users/me")
  await expect(body.locator('[data-testid^="log-entry-"]').first()).toContainText("users/me")
  const shown = await body.locator('[data-testid^="log-entry-"]').allInnerTexts()
  expect(shown.every((text) => text.includes("users/me"))).toBe(true)

  // Errors only: every line left is one.
  await page.getByTestId("logs-search").fill("")
  await page.getByTestId("logs-level").click()
  await page.getByRole("option", { name: "Errors", exact: true }).click()
  await expect(body.locator('[data-testid="log-entry-INFO"]')).toHaveCount(0)
})

test("an error says its ref, and opens to what it was and where it came from", async ({ page }) => {
  const now = new Date().toISOString()
  await page.route(/\/api\/v1\/logs\/(\?.*)?$/, (route) => route.fulfill({
    json: {
      kept: true,
      more: false,
      entries: [
        {
          time: now,
          process: "backend",
          level: "ERROR",
          logger: "app.adapters.postgres.session",
          message: "PostgreSQL: Query failed",
          ref: "K7Q3PD",
          request: "POST /api/v1/connectors/1/fetch",
          exception: "Traceback (most recent call last):\n  File \"session.py\", line 471\npsycopg.errors.UndefinedTable: relation \"gone\" does not exist",
        },
        {
          time: now,
          process: "backend",
          level: "INFO",
          logger: "uvicorn.access",
          message: '172.18.0.1:1 - "POST /api/v1/connectors/1/fetch HTTP/1.1" 502',
        },
      ],
    },
  }))
  await login(page)

  for (const theme of ["light", "dark"] as const) {
    await chooseTheme(page, theme)
    // The panel remembers it was open across the reload a theme takes.
    const command = page.getByTestId("command-logs")
    if ((await command.getAttribute("aria-pressed")) !== "true") await command.click()
    const error = page.getByTestId("log-entry-ERROR")
    await expect(error).toContainText("PostgreSQL: Query failed")
    await expect(error.getByTestId("log-entry-ref")).toHaveText("ref K7Q3PD")
    // The answer the person got, in red although uvicorn wrote it at INFO.
    const refused = page.getByTestId("log-entry-INFO").locator(".logs-tool__message")
    const red = await page.evaluate(() => {
      const probe = document.createElement("span")
      probe.className = "dp-tone-text-error"
      document.body.append(probe)
      const colour = getComputedStyle(probe).color
      probe.remove()
      return colour
    })
    await expect(refused).toHaveCSS("color", red)

    await error.getByRole("button").first().click()
    const details = error.getByTestId("log-entry-details")
    await expect(details).toContainText("POST /api/v1/connectors/1/fetch")
    await expect(details.getByTestId("log-entry-exception")).toContainText("UndefinedTable")
    await page.getByTestId("logs-tool").screenshot({ path: `test-results/logs-${theme}.png` })
    // Closed again, so the next theme starts where this one did.
    await error.getByRole("button").first().click()
  }
  await chooseTheme(page, "light")
})

test("somebody who is not a superuser is not offered the log", async ({ page }) => {
  const email = colleagueEmail()
  await login(page)
  await createColleague(page, email)
  await page.goto("/")
  await expect(page.getByTestId("command-logs")).toBeVisible()
  await signOut(page)

  await signInAs(page, email, COLLEAGUE_PASSWORD)
  await expect(page.getByTestId("command-services")).toBeVisible()
  await expect(page.getByTestId("command-logs")).toHaveCount(0)
  const refused = await page.evaluate(async () => {
    const token = Object.entries(localStorage).find(([key]) => key.endsWith("access_token"))?.[1]
    const server = JSON.parse(sessionStorage.getItem("dataplayer:active-server:v1") ?? "null") as { url: string }
    const answer = await fetch(`${server.url}/api/v1/logs/`, { headers: { Authorization: `Bearer ${token ?? ""}` } })
    return answer.status
  })
  expect(refused).toBe(403)

  await signOut(page)
  await login(page)
  await removeColleague(page, email)
})
