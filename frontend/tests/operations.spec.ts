import { expect, test } from "@playwright/test"

import type { JobPublic } from "../src/client"
import { catalogAction } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

test("shows server progress in the footer, opens on demand and cancels from a reusable window", async ({ page }) => {
  let job: JobPublic = {
    id: "12345678-1234-4123-8123-123456789012", kind: "service.create",
    subject_id: null, parameters: null, state: "running",
    step: "pulling the image", step_index: 1, step_count: 6, message: null,
    created_at: new Date().toISOString(), started_at: new Date().toISOString(), finished_at: null,
  }
  let cancelled = 0
  await page.route("**/api/v1/jobs/**", async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().url()).toContain(`/${job.id}/cancel`)
      cancelled++
      job = { ...job, state: "cancelled", message: "Stopped before it finished", finished_at: new Date().toISOString() }
      await route.fulfill({ json: job })
    } else {
      await route.fulfill({ json: { data: [job], count: 1, active_count: job.state === "running" ? 1 : 0 } })
    }
  })
  await login(page)
  const indicator = page.getByTestId("operations-indicator")
  await expect(indicator).toContainText("Start service")
  await expect(indicator.locator('[role="progressbar"]')).toBeVisible()
  await expect(indicator.locator('[role="progressbar"]')).not.toHaveAttribute("aria-valuenow")
  await expect(page.getByTestId("processes-window")).toHaveCount(0)
  const footerBox = await page.getByTestId("app-footer").boundingBox()
  const buttonBox = await indicator.boundingBox()
  expect(Math.abs((footerBox!.x + footerBox!.width) - (buttonBox!.x + buttonBox!.width))).toBeLessThan(30)

  await indicator.click()
  const window = page.getByRole("dialog", { name: "Processes", exact: true })
  await expect(window).toContainText("pulling the image (1 of 6)")
  await expect(window.getByRole("button", { name: "Pause after current" })).toHaveCount(0)
  await window.getByRole("button", { name: "Minimize", exact: true }).click()
  await expect(window).toBeHidden()
  await indicator.click()
  await expect(window).toBeVisible()
  await expect(page.getByTestId("processes-window")).toHaveCount(1)
  await window.getByRole("button", { name: "Close window", exact: true }).click()
  expect(cancelled).toBe(0)
  await expect(indicator.locator('[role="progressbar"]')).toBeVisible()

  await indicator.click()
  await window.getByRole("button", { name: "Cancel job", exact: true }).click()
  await expect(window).toContainText("Stopped before it finished")
  expect(cancelled).toBe(1)
  await expect(indicator.locator('[role="progressbar"]')).toHaveCount(0)
  await page.reload()
  await expect(page.getByTestId("processes-window")).toHaveCount(0)
  await indicator.click()
  await expect(window).toContainText("Stopped before it finished")
  await window.getByRole("button", { name: "Clear finished", exact: true }).click()
  await expect(window).toContainText("No processes")
})

test("pauses an upload batch, resumes it and leaves only unsent files after stopping", async ({ page }) => {
  const name = `e2e-processes-${Date.now()}`
  let uploads = 0
  let release: (() => void) | undefined
  await page.route("**/api/v1/jobs/**", (route) => route.fulfill({
    json: { data: [], count: 0, active_count: 0 },
  }))
  // Hold each response at the server boundary. No files are written by this
  // scenario; the UI must wait for the current response before pausing.
  await page.route("**/api/v1/connectors/*/actions/upload/file", async (route) => {
    uploads++
    await new Promise<void>((resolve) => { release = resolve })
    await route.fulfill({ json: { message: "Uploaded", reload_node_ids: [null] } })
  })
  await login(page)
  await createFileConnector(page, name)
  await openConnector(page, name)
  await catalogAction(page, "upload")
  await page.getByTestId("action-file").setInputFiles(
    ["first.csv", "second.csv", "third.csv"].map((filename) => ({
      name: filename, mimeType: "text/csv", buffer: Buffer.from("id\n1\n"),
    }))
  )
  await page.getByTestId("action-submit").click()
  await expect.poll(() => uploads).toBe(1)
  await expect(page.getByTestId("processes-window")).toHaveCount(0)
  await page.getByTestId("operations-indicator").click()
  const window = page.getByRole("dialog", { name: "Processes", exact: true })
  await window.getByRole("button", { name: "Pause after current", exact: true }).click()
  await expect(window).toContainText("Pausing after current")
  release?.()
  await expect(window.getByText("Paused", { exact: true })).toBeVisible()
  expect(uploads).toBe(1)
  await expect(window).toContainText("1 of 3 items processed")
  await window.getByRole("button", { name: "Resume", exact: true }).click()
  await expect.poll(() => uploads).toBe(2)
  await window.getByRole("button", { name: "Stop after current", exact: true }).click()
  release?.()
  await expect(window.getByText("Stopped", { exact: true })).toBeVisible()
  await expect(window).toContainText("1 not started")
  expect(uploads).toBe(2)
  await window.getByRole("button", { name: "Close window", exact: true }).click()
  await expect(page.getByTestId("action-files")).toContainText("third.csv")
  await expect(page.getByTestId("action-files")).not.toContainText("first.csv")
  await expect(page.getByTestId("action-files")).not.toContainText("second.csv")
  await page.getByRole("button", { name: "Cancel", exact: true }).click()
  await deleteConnector(page, name)
})
