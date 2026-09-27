import { expect, test } from "@playwright/test"

import type { JobPublic } from "../src/client"
import { isolateJobAttention } from "./utils/activity"
import { catalogAction } from "./utils/catalog"
import { createFileConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { deleteConnector, openConnector } from "./utils/workspace"

test("shows server progress in the footer, opens the sheet on demand and cancels from it", async ({ page }) => {
  await isolateJobAttention(page)
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
  const indicator = page.getByTestId("activity-indicator")
  // The bell carries the count, and what is running stands beside it with its
  // progress, the way a status bar says it (D113). Hovering names the step.
  await expect(indicator.getByTestId("activity-count")).toHaveText("1")
  const running = page.getByTestId("activity-progress")
  await expect(running).toContainText("Start service")
  await expect(running.getByRole("progressbar")).toBeVisible()
  await indicator.hover()
  await expect(page.locator(".app-tooltip")).toContainText("pulling the image (1 of 6)")
  await expect(page.getByTestId("activity-panel")).toHaveCount(0)
  const footerBox = await page.getByTestId("app-footer").boundingBox()
  const buttonBox = await indicator.boundingBox()
  expect(Math.abs((footerBox!.x + footerBox!.width) - (buttonBox!.x + buttonBox!.width))).toBeLessThan(30)

  await indicator.click()
  const sheet = page.getByTestId("activity-panel")
  await expect(sheet).toContainText("pulling the image (1 of 6)")
  await expect(sheet.getByRole("button", { name: "Pause after current" })).toHaveCount(0)
  // The sheet floats over the work rather than moving it: the workspace keeps
  // the width it had before the sheet was opened (D113).
  const workspace = page.getByTestId("app-footer")
  const before = (await workspace.boundingBox())!.width
  await expect.poll(async () => (await workspace.boundingBox())!.width).toBe(before)

  // Escape closes it, and so does the button that opened it.
  await page.keyboard.press("Escape")
  await expect(sheet).toHaveCount(0)
  await indicator.click()
  await expect(sheet).toBeVisible()
  await indicator.click()
  await expect(sheet).toHaveCount(0)
  expect(cancelled).toBe(0)
  await expect(indicator.getByTestId("activity-count")).toHaveText("1")

  await indicator.click()
  await sheet.getByRole("button", { name: "Cancel job", exact: true }).click()
  await expect(sheet).toContainText("Stopped before it finished")
  expect(cancelled).toBe(1)
  // Nothing runs any more, so the bar goes and the button stops naming the
  // step: only the standing offer to show the activity is left hovering it.
  await expect(running).toHaveCount(0)
  await indicator.hover()
  await expect(page.locator(".app-tooltip")).toContainText("Show activity")
  await expect(page.locator(".app-tooltip")).not.toContainText("pulling the image")
  // Ended, the job leaves Working for one entry in Recent (D181), and a
  // reload reads that entry again from the server.
  await expect(sheet.getByTestId("working-section")).toContainText("Nothing is running")
  await page.reload()
  await expect(page.getByTestId("activity-panel")).toHaveCount(0)
  await indicator.click()
  await expect(sheet.getByTestId("working-section")).toContainText("Nothing is running")
  const ending = sheet.getByTestId("notice").filter({ hasText: "Stopped before it finished" })
  await expect(ending).toHaveCount(1)
  // Waved away, it stays away after the next reload too.
  await ending.getByRole("button", { name: "Remove", exact: true }).click()
  await page.reload()
  await indicator.click()
  await expect(sheet.getByTestId("notice").filter({ hasText: "Stopped before it finished" })).toHaveCount(0)
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
  await expect(page.getByTestId("activity-panel")).toHaveCount(0)
  await page.getByTestId("activity-indicator").click()
  const window = page.getByTestId("activity-panel")
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
  // Stopped, it leaves Working (D181): what became of it is said once, in
  // the window that asked, which keeps the file that was never sent.
  await expect(window.getByTestId("working-section")).toContainText("Nothing is running")
  expect(uploads).toBe(2)
  await page.keyboard.press("Escape")
  await expect(page.getByTestId("action-files")).toContainText("third.csv")
  await expect(page.getByTestId("action-error")).toContainText("Not started: the queue was stopped")
  await expect(page.getByTestId("action-files")).not.toContainText("first.csv")
  await expect(page.getByTestId("action-files")).not.toContainText("second.csv")
  await page.getByRole("button", { name: "Cancel", exact: true }).click()
  await deleteConnector(page, name)
})
