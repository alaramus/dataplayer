import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { expectFieldActionAligned } from "./utils/layout"
import { login } from "./utils/login"

const SERVICE = {
  id: "layout-service", template_key: "postgres", title: "PostgreSQL", state: "running",
  container_state: "running", container_name: "dataplayer-layout", published_port: 55432,
  connector_id: "layout-connector", connector_name: "Layout service", was_connected: true,
  created_at: "2026-09-21T00:00:00Z", job: null,
}
const CREDENTIALS = {
  host: "127.0.0.1", port: 55432, user: "postgres", database: "postgres", password_mode: "generated",
  url: `postgresql://postgres@127.0.0.1:55432/postgres?application_name=${"example".repeat(12)}`,
  unreachable_reason: "The service listens on this machine only, so another computer cannot reach it at this address.",
}

// The window as it is opened from the list of services; the one that hands a
// password over is opened by starting a service, in services.spec.ts. Routed
// before signing in, because the workspace asks for its services on arrival.
async function serveOneService(page: Page) {
  await page.route(/\/api\/v1\/services\/(\?.*)?$/, (route) => route.request().method() === "GET"
    ? route.fulfill({ json: [SERVICE] })
    : route.fallback())
  let answer: () => void = () => undefined
  const answered = new Promise<void>((resolve) => { answer = resolve })
  await page.route("**/api/v1/services/layout-service/credentials", async (route) => {
    await answered
    await route.fulfill({ json: CREDENTIALS })
  })
  return answer
}

async function openCredentials(page: Page) {
  await page.getByTestId("command-services").click()
  await page.getByTestId("credentials-service-layout-service").click()
  const content = page.getByTestId("service-credentials-dialog")
  return { content, frame: page.getByRole("dialog").filter({ has: content }) }
}

for (const theme of ["light", "dark"] as const) {
  test(`service address keeps compact read-only fields in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    const answer = await serveOneService(page)
    await login(page)
    const { content, frame } = await openCredentials(page)
    await expect(frame).toHaveAccessibleName("Connecting to Layout service")
    const before = await frame.boundingBox()
    answer()

    const rows = [["credential-host", "Host", "127.0.0.1"], ["credential-port", "Port", "55432"],
      ["credential-user", "User", "postgres"], ["credential-database", "Database", "postgres"],
      ["credential-url", "URL", CREDENTIALS.url]] as const
    for (const [id, name, value] of rows) {
      const field = page.getByTestId(id)
      await expect(field).toHaveValue(value)
      await expect(field).toHaveAccessibleName(name)
      await expect(field).toHaveAttribute("readonly", "")
      // Read character by character, where l and I must differ.
      await expect(field).toHaveCSS("font-family", /monospace/)
      const label = await frame.getByText(name, { exact: true }).boundingBox()
      const box = await field.boundingBox()
      if (!label || !box) throw new Error(`Missing ${name}`)
      expect(label.x + label.width).toBeLessThan(box.x)
      expect(box.height).toBeLessThanOrEqual(36)
    }
    await expect(page.getByTestId("credential-password")).toHaveCount(0)
    await expect(page.getByTestId("credential-password-note")).toContainText("was shown once")
    await expect(content).toContainText(CREDENTIALS.unreachable_reason)
    await expectFieldActionAligned(page.getByTestId("credential-url"), page.getByTestId("copy-url"))
    // Loading the answer after the window opened does not move or resize it (D132).
    expect(await frame.boundingBox()).toEqual(before)
    const body = content.locator(".window-dialog__content")
    expect(await body.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    await frame.screenshot({ path: `test-results/service-credentials-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expect.poll(async () => {
      const label = await frame.getByText("Host", { exact: true }).boundingBox()
      const field = await page.getByTestId("credential-host").boundingBox()
      return label && field ? field.y - label.y - label.height : -1
    }).toBeGreaterThanOrEqual(0)
    await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("credentials-done")).toBeInViewport()
    await frame.screenshot({ path: `test-results/service-credentials-${theme}-narrow.png` })
    await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect(page.getByTestId("copy-url")).toBeInViewport()
    await expect(page.getByTestId("credentials-done")).toBeInViewport()
    await page.getByTestId("credentials-done").click()
    await expect(content).toHaveCount(0)
  })
}
