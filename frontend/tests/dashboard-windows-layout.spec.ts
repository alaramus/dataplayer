import { expect, test } from "@playwright/test"
import type { Page, Route } from "@playwright/test"

import { login } from "./utils/login"

/**
 * The dashboards windows keep their frame while what they ask for arrives, and
 * reflow without horizontal overflow at a narrow width (slice 24). The metrics
 * APIs are stubbed, so no store, agent or adapter answer is needed from the
 * stack.
 */

function gate() {
  let release: () => void = () => undefined
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  return { held, release }
}

async function hold(page: Page, pattern: string, json: unknown) {
  const { held, release } = gate()
  await page.route(pattern, async (route: Route) => {
    await held
    await route.fulfill({ json })
  })
  return release
}

async function stubStoreReady(page: Page) {
  await page.route("**/api/v1/metrics/store", (route) =>
    route.fulfill({ json: { state: "ready", may_set_up: true } })
  )
}

async function stubDashboards(page: Page) {
  await page.route("**/api/v1/metrics/dashboards", (route) =>
    route.fulfill({
      json: [
        {
          id: "layout-dashboard",
          name: "Layout dashboard",
          version: 1,
          updated_at: "2026-09-21T00:00:00Z",
          widgets: [],
          access: "own",
        },
      ],
    })
  )
}

async function expectNoHorizontalOverflow(dialog: ReturnType<Page["getByTestId"]>) {
  const body = dialog.locator(".window-dialog__content")
  await expect.poll(() => body.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
}

for (const theme of ["light", "dark"] as const) {
  test(`the add-widgets window keeps its frame while the catalog arrives in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await stubStoreReady(page)
    await stubDashboards(page)
    const releaseCatalog = await hold(page, "**/api/v1/metrics/catalog", {
      agents: [
        {
          agent_id: "agent-1",
          name: "watcher",
          hosts: [
            {
              host: "web-01",
              last_seen: "2026-09-21T00:00:00Z",
              metrics: [
                {
                  metric: "cpu",
                  series: [
                    {
                      id: 1,
                      field: "utilization",
                      label: "total",
                      unit: "%",
                      first_seen: "2026-09-21T00:00:00Z",
                      last_seen: "2026-09-21T00:00:00Z",
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
      connectors: [],
    })
    const releasePresets = await hold(page, "**/api/v1/metrics/presets**", [])

    await login(page)
    await page.getByTestId("space-dashboards").click()
    await page.getByTestId("dashboard-Layout dashboard").click()
    await page.getByTestId("dashboard-add").click()
    const dialog = page.getByTestId("add-widgets")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(dialog.getByText("Nothing has reported anything yet")).toBeVisible()
    const before = await frame.boundingBox()

    releaseCatalog()
    await expect(page.getByTestId("add-widgets-tree").getByText("web-01", { exact: true })).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await page.getByTestId("add-widgets-tree").getByText("web-01", { exact: true }).click()
    releasePresets()
    await expect(page.getByTestId("add-widgets-presets")).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/dashboard-add-widgets-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(page.getByTestId("add-widgets-confirm")).toBeInViewport()
    await frame.screenshot({ path: `test-results/dashboard-add-widgets-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  })

  test(`the sources window keeps its frame while an agent key arrives in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await stubStoreReady(page)
    await stubDashboards(page)
    await page.route("**/api/v1/metrics/catalog", (route) => route.fulfill({ json: { agents: [], connectors: [] } }))
    await page.route("**/api/v1/metrics/agents", (route) =>
      route.fulfill({
        json: [
          {
            id: "agent-1",
            name: "watcher",
            created_at: "2026-09-21T00:00:00Z",
            key_issued_at: "2026-09-21T00:00:00Z",
            last_heard_at: null,
          },
        ],
      })
    )
    await page.route("**/api/v1/metrics/hosts", (route) => route.fulfill({ json: [] }))
    await page.route("**/api/v1/metrics/connectors", (route) => route.fulfill({ json: [] }))
    const releaseKey = await hold(page, "**/api/v1/metrics/agents/agent-1/key", {
      agent: {
        id: "agent-1",
        name: "watcher",
        created_at: "2026-09-21T00:00:00Z",
        key_issued_at: "2026-09-21T00:00:00Z",
        last_heard_at: null,
      },
      key: "a".repeat(48),
      udp_port: 9999,
    })

    await login(page)
    await page.getByTestId("space-dashboards").click()
    await page.getByTestId("agents-open").click()
    const dialog = page.getByTestId("agents-dialog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    const registerRow = dialog.getByTestId("agent-register-row")
    const registerAlignment = async () => registerRow.evaluate((row) => {
      const parts = [":scope > span", ".q-field__control", '[data-testid="agent-register"]']
        .map((selector) => row.querySelector(selector)?.getBoundingClientRect())
      if (parts.some((part) => part === undefined)) return false
      const centers = parts.map((part) => part!.top + part!.height / 2)
      return Math.max(...centers) - Math.min(...centers) < 3
    })
    expect(await registerAlignment()).toBe(true)
    await expect(registerRow.locator(".q-field")).toHaveClass(/q-field--outlined/)
    await expect(page.getByTestId("agents-table").getByText("watcher")).toBeVisible()
    const before = await frame.boundingBox()

    await page.getByTestId("agent-key-watcher").click()
    releaseKey()
    await expect(page.getByTestId("agent-key-panel")).toBeVisible()
    await expect(page.getByTestId("agent-snippet")).toContainText('DPM_KEY: "')
    // How to start the agent comes up where it can be seen, not under a list
    // of connections nobody scrolls past.
    await expect(page.getByTestId("agent-snippet")).toBeInViewport()
    await expect(dialog.getByTestId("reporting-table")).toHaveCount(0)
    // The other view starts at its top, with the way back in sight.
    await dialog.getByTestId("agents-view-connections").click()
    await expect(dialog.getByTestId("agents-views")).toBeInViewport()
    await dialog.getByTestId("agents-view-agents").click()
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/dashboard-agents-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    expect(await registerAlignment()).toBe(true)
    await expectNoHorizontalOverflow(dialog)
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeInViewport()
    await frame.screenshot({ path: `test-results/dashboard-agents-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Close", exact: true }).click()
  })

  test(`the store window keeps its frame while the store's facts arrive in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await stubStoreReady(page)
    await page.route("**/api/v1/metrics/dashboards", (route) => route.fulfill({ json: [] }))
    await page.route("**/api/v1/metrics/catalog", (route) => route.fulfill({ json: { agents: [], connectors: [] } }))
    const releaseUsage = await hold(page, "**/api/v1/metrics/store/usage", {
      origin: "connected",
      address: "timescale.example.test:5432/metrics",
      bytes: 1048576,
      series: 42,
      tiers: [{ name: "raw", width_seconds: 15, kept_seconds: 604800 }],
    })

    await login(page)
    await page.getByTestId("space-dashboards").click()
    await page.getByTestId("store-open").click()
    const dialog = page.getByTestId("store-dialog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(dialog.locator(".q-spinner")).toBeVisible()
    const before = await frame.boundingBox()

    releaseUsage()
    await expect(page.getByTestId("store-origin")).toBeVisible()
    await expect(page.getByTestId("store-size")).toContainText("series")
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/dashboard-store-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(dialog.getByRole("button", { name: "Close", exact: true })).toBeInViewport()
    await frame.screenshot({ path: `test-results/dashboard-store-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Close", exact: true }).click()
  })

  test(`the store-connect window keeps its frame while the fields arrive in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await page.route("**/api/v1/metrics/store", (route) =>
      route.fulfill({
        json: {
          state: "not_configured",
          may_set_up: true,
          start: { available: false, reason: "Services cannot be started here" },
        },
      })
    )
    const releaseTypes = await hold(page, "**/api/v1/adapter-types**", [
      {
        name: "postgres",
        title: "PostgreSQL",
        category: "sql",
        category_title: "Databases",
        catalog_shape: "levels",
        description: "A PostgreSQL database.",
        capabilities: [],
        cache_windows: null,
        options_schema: {
          type: "object",
          title: "PostgreSQL",
          properties: {
            host: { type: "string", title: "Host", default: "localhost" },
            port: { type: "integer", title: "Port", default: 5432 },
            user: { type: "string", title: "User" },
            password: { type: "string", title: "Password" },
            dbname: { type: "string", title: "Database" },
          },
          required: ["host", "user", "password", "dbname"],
        },
      },
    ])

    await login(page)
    await page.getByTestId("space-dashboards").click()
    await expect(page.getByTestId("store-setup")).toBeVisible()
    await page.getByTestId("store-connect").click()
    const dialog = page.getByTestId("store-connect-dialog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(dialog).toBeVisible()
    const before = await frame.boundingBox()

    releaseTypes()
    await expect(dialog.locator(".app-form .q-field").first()).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/dashboard-store-connect-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(page.getByTestId("store-connect-confirm")).toBeInViewport()
    await frame.screenshot({ path: `test-results/dashboard-store-connect-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  })
}
