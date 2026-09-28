import { expect, test } from "@playwright/test"
import type { Page, Route } from "@playwright/test"

import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

/**
 * The entry windows keep their frame while what they ask for arrives or the
 * mode switches, and reflow without horizontal overflow at a narrow width
 * (slice 25). The APIs behind them are stubbed, so no adapter list, container
 * or second server is needed from the stack.
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

async function expectNoHorizontalOverflow(dialog: ReturnType<Page["getByTestId"]>) {
  const body = dialog.locator(".window-dialog__content, .server-switcher__body")
  await expect.poll(() => body.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
}

const ADAPTER_TYPES = [
  {
    name: "postgres",
    title: "PostgreSQL",
    category: "sql",
    category_title: "Databases",
    catalog_shape: "levels",
    description: "A PostgreSQL database.",
    can_see: [],
    can_change: [],
    capabilities: [],
    cache_windows: null,
    options_schema: { type: "object", title: "PostgreSQL", properties: {} },
  },
  {
    name: "redis",
    title: "Redis",
    category: "keyvalue",
    category_title: "Key-value stores",
    catalog_shape: "levels",
    description: "A Redis store.",
    can_see: [],
    can_change: [],
    capabilities: [],
    cache_windows: null,
    options_schema: { type: "object", title: "Redis", properties: {} },
  },
]

for (const theme of ["light", "dark"] as const) {
  test(`the adapter catalog keeps its frame while the types arrive in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await page.route("**/api/v1/services/templates", (route) => route.fulfill({ json: [] }))
    const releaseTypes = await hold(page, "**/api/v1/adapter-types**", ADAPTER_TYPES)

    await login(page)
    await page.getByTestId("add-connector").click()
    const dialog = page.getByTestId("adapter-catalog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(dialog.locator(".q-spinner")).toBeVisible()
    const before = await frame.boundingBox()

    releaseTypes()
    await expect(page.getByTestId("adapter-postgres")).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await page.getByTestId("adapter-search").fill("post")
    await expect(page.getByTestId("adapter-postgres")).toBeVisible()
    await expect(page.getByTestId("adapter-redis")).toHaveCount(0)
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/entry-adapter-catalog-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(dialog.getByRole("button", { name: "Cancel", exact: true })).toBeInViewport()
    await frame.screenshot({ path: `test-results/entry-adapter-catalog-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  })

  test(`the server panel keeps its frame from list to edit to the check answer in ${theme}`, async ({ page, context }) => {
    await page.emulateMedia({ colorScheme: theme })
    await page.route("**/api/v1/utils/server-info", (route) =>
      route.fulfill({ json: { product: "dataplayer", client_api_version: 1 } })
    )
    await context.route(/^https:\/\/alpha\.dataplayer\.test\//, async (route) => {
      await route.fulfill({
        contentType: "application/json",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ product: "dataplayer", client_api_version: 1 }),
      })
    })

    await page.goto("/login")
    await page.getByTestId("server-switcher").click()
    const dialog = page.getByTestId("server-manager")
    const frame = dialog
    await expect(page.getByTestId("server-profile").first()).toBeVisible()
    const before = await frame.boundingBox()

    await page.getByTestId("server-add").click()
    await expect(page.getByTestId("server-name")).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await page.getByTestId("server-name").fill("Alpha")
    await page.getByTestId("server-url").fill("https://alpha.dataplayer.test")
    await dialog.getByRole("button", { name: "Check connection", exact: true }).click()
    await expect(page.getByTestId("server-notice")).toContainText("Compatible DataPlayer server.")
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/entry-server-switcher-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(page.getByTestId("server-save")).toBeInViewport()
    await frame.screenshot({ path: `test-results/entry-server-switcher-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
  })


  test(`the tab-group name window keeps its frame when the name error appears in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await expect(page.getByTestId("save-tab-group")).toBeDisabled()
    // Something open to save: a catalog, which is a tab of Data.
    const name = `e2e-group-name-${Date.now()}`
    await createFileConnector(page, name)
    await openConnector(page, name)
    await page.getByTestId("save-tab-group").click()
    const dialog = page.getByTestId("tab-group-name-dialog")
    const frame = page.getByRole("dialog").filter({ has: dialog })
    await expect(page.getByTestId("tab-group-name")).toBeVisible()
    const before = await frame.boundingBox()

    await page.getByTestId("tab-group-name").fill("   ")
    await expect(dialog.getByText("Enter a group name.")).toBeVisible()
    expect(await frame.boundingBox()).toEqual(before)

    await expectNoHorizontalOverflow(dialog)
    await frame.screenshot({ path: `test-results/entry-tab-group-name-${theme}.png` })

    await page.setViewportSize({ width: 390, height: 600 })
    await expectNoHorizontalOverflow(dialog)
    await expect(page.getByTestId("confirm-tab-group-name")).toBeInViewport()
    await frame.screenshot({ path: `test-results/entry-tab-group-name-${theme}-narrow.png` })
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click()
    await page.setViewportSize({ width: 1500, height: 850 })
    await deleteConnector(page, name)
  })
}
