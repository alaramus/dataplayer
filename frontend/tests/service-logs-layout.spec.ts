import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"

const SERVICE = {
  id: "logs-layout-service", template_key: "postgres", title: "PostgreSQL", state: "failed",
  container_state: "exited", container_name: "dataplayer-logs-layout", published_port: null,
  connector_id: null, connector_name: "Logs layout service", was_connected: false,
  created_at: "2026-09-21T00:00:00Z", job: null,
}
const LINES = Array.from({ length: 260 }, (_, index) =>
  `2026-09-21T10:00:${String(index % 60).padStart(2, "0")}Z ERROR service output line ${String(index + 1).padStart(3, "0")} ${"details ".repeat(8)}`)

async function serveServiceLogs(page: Page) {
  await page.route(/\/api\/v1\/services\/(\?.*)?$/, (route) => route.request().method() === "GET"
    ? route.fulfill({ json: [SERVICE] })
    : route.fallback())
  let release: () => void = () => undefined
  let held = new Promise<void>((resolve) => { release = resolve })
  await page.route("**/api/v1/services/logs-layout-service/logs", async (route) => {
    await held
    await route.fulfill({ json: { lines: LINES } })
  })
  return {
    hold() { held = new Promise<void>((resolve) => { release = resolve }) },
    release() { release() },
  }
}

for (const theme of ["light", "dark"] as const) {
  test(`service logs fill a stable window and scroll in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    const logs = await serveServiceLogs(page)
    await login(page)
    await page.getByTestId("command-services").click()
    await page.getByTestId("logs-service-logs-layout-service").click()

    const content = page.getByTestId("service-logs")
    const frame = page.getByRole("dialog").filter({ has: content })
    const region = content.locator(".service-logs")
    const before = await frame.boundingBox()
    await expect(region.locator(".q-spinner")).toBeVisible()
    expect(await region.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    logs.release()
    await expect(region).toContainText(LINES[0] ?? "")
    expect(await frame.boundingBox()).toEqual(before)
    await expect(content).toContainText("The last lines this service printed.")
    await expect(frame).toHaveAccessibleName("Output of Logs layout service")

    const header = content.locator(".window-dialog__subtitle")
    const actions = frame.locator(".app-window__bar")
    const initialHeader = await header.boundingBox()
    const initialActions = await actions.boundingBox()
    expect(await region.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
    await region.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect.poll(() => region.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
    expect(await header.boundingBox()).toEqual(initialHeader)
    expect(await actions.boundingBox()).toEqual(initialActions)
    await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await frame.screenshot({ path: `test-results/service-logs-${theme}-wide.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expect.poll(() => frame.evaluate((el) => el.getBoundingClientRect().width <= innerWidth)).toBe(true)
    await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(page.getByTestId("window-to-tab")).toBeInViewport()
    await expect(frame.getByRole("button", { name: "Close window" })).toBeInViewport()
    await frame.screenshot({ path: `test-results/service-logs-${theme}-narrow.png` })
    await page.getByTestId("window-to-tab").click()
    await expect(content).toHaveCount(0)
  })
}
