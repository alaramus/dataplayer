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
    await expect(region.locator(":scope > .row.justify-center .q-spinner")).toBeVisible()
    expect(await region.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
    logs.release()
    await expect(region).toContainText(LINES[0] ?? "")
    const controls = region.locator(".service-logs__controls")
    const output = region.locator(".service-logs__text")
    expect(await controls.evaluate((el) => getComputedStyle(el).backgroundColor))
      .toBe(await region.evaluate((el) => getComputedStyle(el).backgroundColor))
    expect((await controls.boundingBox())!.y + (await controls.boundingBox())!.height)
      .toBeLessThanOrEqual((await output.boundingBox())!.y)
    expect(await frame.boundingBox()).toEqual(before)
    await expect(content.locator(".window-dialog__subtitle")).toHaveCount(0)
    await expect(frame).toHaveAccessibleName("Output of Logs layout service")

    const actions = frame.locator(".app-window__bar")
    const initialActions = await actions.boundingBox()
    expect(await region.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
    await region.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await expect.poll(() => region.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
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

test("service logs can be refreshed manually or on a chosen interval in a window and tab", async ({ page }) => {
  await page.route(/\/api\/v1\/services\/(\?.*)?$/, (route) => route.request().method() === "GET"
    ? route.fulfill({ json: [SERVICE] })
    : route.fallback())
  let reads = 0
  await page.route("**/api/v1/services/logs-layout-service/logs", (route) => {
    reads += 1
    return route.fulfill({ json: { lines: [`Read ${String(reads)}`] } })
  })
  await login(page)
  await page.getByTestId("command-services").click()
  await page.getByTestId("logs-service-logs-layout-service").click()
  const window = page.getByTestId("service-logs")
  await expect(window).toContainText("Read 1")
  const refreshInterval = window.getByTestId("service-logs-auto-refresh")
  await expect(refreshInterval).toHaveAttribute("data-refresh", "5")
  await refreshInterval.click()
  await page.getByTestId("menu-item-off").click()
  await window.getByTestId("service-logs-refresh").click()
  await expect(window).toContainText("Read 2")

  await refreshInterval.click()
  await page.getByTestId("menu-item-s1").click()
  await expect(window.getByTestId("service-logs-auto-refresh")).toHaveAttribute("data-refresh", "1")
  await expect.poll(() => reads).toBeGreaterThan(3)

  await page.getByTestId("window-to-tab").click()
  const tabLogs = page.getByTestId("service-logs-auto-refresh")
  await expect(tabLogs).toHaveAttribute("data-refresh", "1")
  await expect(page.getByTestId("service-logs-refresh")).toBeVisible()
})
