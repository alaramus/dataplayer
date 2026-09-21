import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { dismissToast } from "./utils/notices"
import { deleteConnector, openConnector } from "./utils/workspace"

const FILES = Array.from({ length: 12 }, (_, i) => ({
  filename: `layout-example-with-a-long-name-${String(i + 1).padStart(2, "0")}-2026-09-21T10-00-00.dump`,
  size_bytes: 1_048_576 * (i + 1),
  modified_at: 1_790_000_000 + i * 3600,
}))

// Answers are held until `release`, so what arrives after the window opens is
// measured against the window that was already there. The list is asked for
// when the catalog opens, so this is routed before that. Nothing is copied,
// restored or deleted.
async function serveBackups(page: Page) {
  let held = Promise.resolve()
  let open: () => void = () => undefined
  const state = {
    available: true,
    hold() { held = new Promise<void>((resolve) => { open = resolve }) },
    release() { open() },
  }
  state.hold()
  await page.route("**/api/v1/backups/offer?*", async (route) => {
    await held
    await route.fulfill({ json: state.available
      ? { available: true, folder: "backups" }
      : { available: false, reason: "This server has no container runtime to copy a database out with." } })
  })
  await page.route(/\/api\/v1\/backups\/(\?.*)?$/, async (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    await held
    await route.fulfill({ json: FILES })
  })
  return state
}

async function openBackups(page: Page) {
  await page.getByTestId("catalog-actions").click()
  await page.getByTestId("menu-item-client:backups").click()
  const content = page.getByTestId("backups-dialog")
  await expect(content).toBeVisible()
  return { content, frame: page.getByRole("dialog").filter({ has: content }) }
}

for (const theme of ["light", "dark"] as const) {
  test(`backups keep a flat list above the footer action in ${theme}`, async ({ page }) => {
    const name = `e2e-backups-layout-${theme}-${Date.now()}`
    await page.emulateMedia({ colorScheme: theme })
    await login(page)
    await createPostgresConnector(page, name)
    await dismissToast(page, "Connection saved")
    const backups = await serveBackups(page)
    try {
      await openConnector(page, name)
      let { content, frame } = await openBackups(page)
      const before = await frame.boundingBox()
      backups.release()

      const first = page.getByTestId(`backup-${FILES[0]?.filename ?? ""}`)
      await expect(first).toContainText("1.0 MB")
      await expect(page.getByTestId("take-backup")).toBeEnabled()
      // Loading the list after the window opened does not move or resize it (D132).
      expect(await frame.boundingBox()).toEqual(before)
      // The one thing the window is for is its footer's primary action.
      await expect(content.locator(".window-dialog__actions").getByTestId("take-backup")).toBeVisible()
      await expect(frame.getByRole("button", { name: "Close", exact: true })).toBeVisible()
      // Rows sit on the window's surface rather than on cards of their own.
      const surfaces = await content.evaluate((el) => {
        const row = el.querySelector('[data-testid^="backup-"]')
        return row ? [getComputedStyle(row).backgroundColor, getComputedStyle(row).borderRadius] : null
      })
      expect(surfaces).toEqual(["rgba(0, 0, 0, 0)", "0px"])
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      const body = content.locator(".window-dialog__content")
      expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
      await frame.screenshot({ path: `test-results/backups-${theme}.png` })
      await body.evaluate((el) => { el.scrollTop = el.scrollHeight })
      await expect(page.getByTestId(`restore-${FILES.at(-1)?.filename ?? ""}`)).toBeInViewport()
      await expect(page.getByTestId("take-backup")).toBeInViewport()

      await page.setViewportSize({ width: 390, height: 600 })
      await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      await expect(page.getByTestId("take-backup")).toBeInViewport()
      await expect(page.getByTestId(`restore-${FILES.at(-1)?.filename ?? ""}`)).toBeVisible()
      await frame.screenshot({ path: `test-results/backups-${theme}-narrow.png` })
      await frame.getByRole("button", { name: "Close", exact: true }).click()
      await expect(content).toHaveCount(0)

      // Where nothing can be copied out, the window says why, and only deleting
      // a file stays on offer.
      await page.setViewportSize({ width: 1280, height: 720 })
      backups.available = false
      backups.hold()
      ;({ content, frame } = await openBackups(page))
      const closed = await frame.boundingBox()
      backups.release()
      await expect(content).toContainText("no container runtime")
      await expect(page.getByTestId("take-backup")).toBeDisabled()
      await expect(page.getByTestId(`restore-${FILES[0]?.filename ?? ""}`)).toBeDisabled()
      await expect(page.getByTestId(`delete-backup-${FILES[0]?.filename ?? ""}`)).toBeEnabled()
      expect(await frame.boundingBox()).toEqual(closed)
      await frame.screenshot({ path: `test-results/backups-${theme}-unavailable.png` })
      await frame.getByRole("button", { name: "Close", exact: true }).click()
    } finally {
      await deleteConnector(page, name)
    }
  })
}
