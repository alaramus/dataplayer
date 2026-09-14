import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

test("opens, restores and manages the application agent space", async ({ page }) => {
  await login(page)

  await page.getByTestId("space-ai").click()
  await expect(page.getByTestId("space-ai")).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("ai-space")).toBeVisible()
  await expect(page.getByTestId("ai-space").getByTestId("workspace-separator")).toBeVisible()
  await expect(page.getByTestId("ai-rail")).toBeVisible()
  await expect(page.getByTestId("ai-conversation-card")).toBeVisible()
  const railBackground = await page.getByTestId("ai-rail").evaluate((element) => getComputedStyle(element).backgroundColor)
  await expect(page.getByTestId("ai-conversation-card")).toHaveCSS("background-color", railBackground)

  await page.getByTestId("ai-collapse-history").click()
  await expect(page.getByTestId("ai-history")).toHaveCount(0)
  await expect(page.getByTestId("ai-new-chat")).toHaveAttribute("aria-label", "New chat")
  await expect(page.getByTestId("ai-open-settings")).toHaveAttribute("aria-label", "Settings")
  await page.getByTestId("ai-collapse-history").click()

  await page.getByTestId("ai-new-chat").click()
  const active = page.locator('[data-testid^="ai-chat-row-"][data-active="true"]')
  await expect(active).toBeVisible()
  const conversationId = (await active.getAttribute("data-testid"))?.replace("ai-chat-row-", "")
  expect(conversationId).toBeTruthy()

  await active.getByRole("button", { name: "Rename chat" }).click()
  await active.getByRole("textbox", { name: "Chat title" }).fill("Playwright agent chat")
  await active.getByRole("textbox", { name: "Chat title" }).press("Enter")
  await expect(active).toContainText("Playwright agent chat")

  await page.reload()
  await expect(page.getByTestId("space-ai")).toHaveAttribute("aria-pressed", "true")
  await expect(page.getByTestId("ai-space")).toBeVisible()
  await expect(page.getByTestId(`ai-chat-row-${conversationId ?? ""}`)).toHaveAttribute("data-active", "true")

  await page.getByTestId("space-data").click()
  await expect(page.getByTestId("ai-space")).toHaveCount(0)
  await page.getByTestId("space-ai").click()
  await expect(page.getByTestId(`ai-chat-row-${conversationId ?? ""}`)).toHaveAttribute("data-active", "true")

  await page.getByTestId("ai-open-settings").click()
  await expect(page.getByTestId("ai-settings")).toBeVisible()
  await expect(page.getByTestId("ai-model")).toBeVisible()
  await expect(page.getByTestId("ai-allow-all")).toBeVisible()

  await page.getByTestId("ai-model").click()
  const providerKey = page.getByRole("button", { name: /Manage .* API key/ }).first()
  await expect(providerKey).toBeVisible()
  await providerKey.click()
  await expect(page.getByTestId("ai-key-dialog")).toBeVisible()
  await expect(page.getByTestId("ai-provider-key")).toBeVisible()
  await page.getByTestId("ai-key-dialog").getByRole("button", { name: "Close" }).click()

  const row = page.getByTestId(`ai-chat-row-${conversationId ?? ""}`)
  await row.getByRole("button", { name: "Delete chat" }).click()
  await page.getByRole("dialog", { name: "Delete chat?" }).getByRole("button", { name: "Delete" }).click()
  await expect(row).toHaveCount(0)
})
