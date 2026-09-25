import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("opening and closing a quick chat leaves history unchanged", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-ai").click()
  const rows = page.locator('[data-testid^="ai-chat-row-"]')
  const before = await rows.count()
  await page.getByTestId("quick-chat-rail").click()
  await expect(page.getByTestId("quick-chat-window")).toBeVisible()
  await page.getByRole("button", { name: "Close window" }).click()
  await expect(rows).toHaveCount(before)
})

test("quick chat uses the same history and archive actions as agent chat", async ({ page }) => {
  await login(page)
  const token = await page.evaluate(() => Object.entries(localStorage)
    .find(([key]) => key.endsWith("access_token"))?.[1])
  expect(token).toBeTruthy()
  const server = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dataplayer:active-server:v1") ?? "null"
  ) as { url: string })
  const created = await page.request.post(`${server.url}/api/v1/ai/quick-chats`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(created.ok(), await created.text()).toBe(true)
  const id = (await created.json()).id as string

  await page.getByTestId("space-ai").click()
  const row = page.getByTestId(`ai-chat-row-${id}`)
  await expect(row).toBeVisible()
  await expect(row.getByTestId(`ai-chat-${id}`).locator(".q-icon")).toHaveCount(0)
  await expect(row.getByTestId(`quick-chat-delete-${id}`)).toHaveCount(0)
  await row.hover()
  await row.getByTestId(`ai-pin-${id}`).click()
  await row.hover()
  await row.getByTestId(`ai-archive-${id}`).click()
  await expect(page.getByTestId(`ai-chat-row-${id}`)).toHaveCount(0)

  await page.getByTestId("ai-open-settings").click()
  const archived = page.getByTestId(`ai-archived-${id}`)
  await expect(archived).toBeVisible()
  await page.getByTestId(`ai-restore-${id}`).click()
  await page.getByTestId("ai-open-settings").click()
  await page.getByTestId(`ai-chat-${id}`).click()
  await expect(page.getByTestId("quick-chat-window")).toBeVisible()
  await page.getByRole("button", { name: "Close window" }).click()
  await row.hover()
  await row.getByTestId(`ai-archive-${id}`).click()
  await page.getByTestId("ai-open-settings").click()
  await page.getByTestId(`ai-delete-${id}`).click()
  await page.getByRole("dialog", { name: "Delete chat?" }).getByRole("button", { name: "Delete" }).click()
  await expect(page.getByTestId(`ai-archived-${id}`)).toHaveCount(0)
})
