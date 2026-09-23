import { expect, test } from "@playwright/test"
import type { Page } from "@playwright/test"

import { login } from "./utils/login"

const SERVICE = {
  id: "layout-running-service", template_key: "postgres", title: "PostgreSQL", state: "running",
  container_state: "running", container_name: "dataplayer-layout-running", published_port: 55432,
  connector_id: "layout-running-connector", connector_name: "Layout running service", was_connected: true,
  created_at: "2026-09-21T00:00:00Z", job: null,
}

async function serveRunningService(page: Page) {
  await page.route(/\/api\/v1\/services\/(\?.*)?$/, (route) => route.request().method() === "GET"
    ? route.fulfill({ json: [SERVICE] })
    : route.fallback())
}

async function checkProjectWindow(page: Page, title: string, screenshotName: string) {
  const content = page.getByTestId("ai-project-dialog")
  const frame = page.getByRole("dialog", { name: title, exact: true })
  await expect(content).toBeVisible()
  const before = await frame.boundingBox()
  const field = page.getByTestId("ai-project-name")
  await expect(field).toBeVisible()
  await expect(field).toBeFocused()
  expect(await frame.boundingBox()).toEqual(before)
  await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  await frame.screenshot({ path: `test-results/${screenshotName}-wide.png` })

  await page.setViewportSize({ width: 390, height: 640 })
  const narrow = await frame.boundingBox()
  expect(narrow).not.toBeNull()
  expect(narrow!.x).toBeGreaterThanOrEqual(0)
  expect(narrow!.x + narrow!.width).toBeLessThanOrEqual(390)
  await expect.poll(() => content.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  await expect(page.getByTestId("ai-project-save")).toBeInViewport()
  await expect(frame.getByRole("button", { name: "Close window" })).toBeInViewport()
  await frame.screenshot({ path: `test-results/${screenshotName}-narrow.png` })
}

for (const theme of ["light", "dark"] as const) {
  test(`AI project windows and services list fit in ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme })
    await serveRunningService(page)
    await login(page)

    await page.getByTestId("space-ai").click()
    await expect(page.getByTestId("ai-space")).toBeVisible()
    await page.getByTestId("ai-new-project").click()
    await checkProjectWindow(page, "New project", `ai-project-new-${theme}`)
    const name = `layout-${theme}-${Date.now()}`
    await page.getByTestId("ai-project-name").fill(name)
    await page.getByTestId("ai-project-name").press("Enter")
    const project = page.locator('[data-testid^="ai-project-toggle-"]').filter({ hasText: name })
    await expect(project).toBeVisible()
    const id = (await project.getAttribute("data-testid"))?.replace("ai-project-toggle-", "") ?? ""

    await page.setViewportSize({ width: 1280, height: 800 })
    await project.hover()
    await page.getByTestId(`ai-project-rename-${id}`).click()
    await checkProjectWindow(page, "Rename project", `ai-project-rename-${theme}`)
    await page.getByTestId("ai-project-name").fill(`${name} updated`)
    await page.getByTestId("ai-project-save").click()
    await expect(project).toContainText(`${name} updated`)

    await page.setViewportSize({ width: 1280, height: 800 })
    await page.getByTestId("command-services").click()
    const panel = page.getByTestId("bottom-panel")
    const list = page.getByTestId("managed-services")
    const row = page.getByTestId(`managed-service-${SERVICE.id}`)
    await expect(row).toContainText("running")
    await expect(row.getByTestId(`logs-service-${SERVICE.id}`)).toBeVisible()
    await expect(row.getByTestId(`credentials-service-${SERVICE.id}`)).toBeVisible()
    const rowChrome = await row.evaluate((el) => ({
      background: getComputedStyle(el).backgroundColor,
      radius: getComputedStyle(el).borderRadius,
    }))
    expect(rowChrome).toEqual({ background: "rgba(0, 0, 0, 0)", radius: "0px" })
    await expect.poll(() => list.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await panel.screenshot({ path: `test-results/services-list-${theme}-wide.png` })

    await page.setViewportSize({ width: 390, height: 640 })
    await expect.poll(() => list.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
    await expect(row.getByTestId(`logs-service-${SERVICE.id}`)).toBeVisible()
    await expect(row.getByTestId(`remove-service-${SERVICE.id}`)).toBeVisible()
    await panel.screenshot({ path: `test-results/services-list-${theme}-narrow.png` })
    await page.getByTestId("bottom-panel-hide").click()

    await project.hover()
    await page.getByTestId(`ai-project-delete-${id}`).click()
    await page.getByRole("dialog", { name: "Delete project?" }).getByRole("button", { name: "Delete" }).click()
    await expect(project).toHaveCount(0)
  })
}
