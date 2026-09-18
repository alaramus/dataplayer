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

  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId("ai-history")).toHaveCount(0)
  await expect(page.getByTestId("ai-new-chat")).toHaveAttribute("aria-label", "New chat")
  await expect(page.getByTestId("ai-open-settings")).toHaveAttribute("aria-label", "Settings")
  await page.getByTestId("app-toggle-first-panel").click()

  const active = page.locator('[data-testid^="ai-chat-row-"][data-active="true"]')
  const previousId = (await active.count()) > 0 ? await active.getAttribute("data-testid") : null
  await page.getByTestId("ai-new-chat").click()
  // Creating a chat is a round trip: the previous row stays active until the new one
  // arrives, so wait for the switch instead of reading whichever row is active
  // immediately after the click.
  if (previousId === null) await expect(active).toBeVisible()
  else await expect(active).not.toHaveAttribute("data-testid", previousId)
  const conversationId = (await active.getAttribute("data-testid"))?.replace("ai-chat-row-", "")
  expect(conversationId).toBeTruthy()

  // The open chat is named above the conversation, and pressing the name is how
  // it is renamed. The strip keeps its height while it holds the field, or the
  // whole conversation jumps down the moment somebody presses the name.
  const head = page.getByTestId("ai-chat-head")
  const closed = (await head.boundingBox())?.height
  await page.getByTestId("ai-chat-heading").click()
  const field = page.getByTestId("ai-rename-input")
  await expect(field).toBeVisible()
  expect((await head.boundingBox())?.height).toBe(closed)
  await field.fill("Playwright agent chat")
  await field.press("Enter")
  await expect(page.getByTestId("ai-chat-heading")).toHaveText("Playwright agent chat")
  expect((await head.boundingBox())?.height).toBe(closed)
  await expect(active).toContainText("Playwright agent chat")

  // The composer follows what is typed and then stops: no corner grip to drag,
  // and a long draft never squeezes the transcript off the card.
  const composer = page.getByTestId("ai-message-input")
  await expect(composer).toHaveCSS("resize", "none")
  await composer.fill("word ".repeat(400))
  expect((await composer.boundingBox())?.height).toBeLessThanOrEqual(150)
  await expect(page.getByTestId("ai-messages")).toBeVisible()
  await composer.fill("")

  // The model is chosen in the chat itself and stays with it; the settings
  // choose only what a new chat starts with.
  await page.getByTestId("ai-chat-model").click()
  await page.getByRole("option", { name: /Claude Opus 5/ }).click()
  await expect(page.getByTestId("ai-chat-model")).toContainText("Claude Opus 5")
  await page.reload()
  await expect(page.getByTestId("ai-chat-model")).toContainText("Claude Opus 5")

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

  // A chat is pinned above the rest and archived out of the history from its
  // row; it is deleted only from the archive, in the settings.
  const id = conversationId ?? ""
  const row = page.getByTestId(`ai-chat-row-${id}`)
  await row.hover()
  await page.getByTestId(`ai-pin-${id}`).click()
  await expect(page.locator('[data-testid^="ai-chat-row-"]').first()).toHaveAttribute(
    "data-testid", `ai-chat-row-${id}`
  )
  await page.getByTestId(`ai-archive-${id}`).click()
  await expect(row).toHaveCount(0)

  await page.getByTestId("ai-open-settings").click()
  const archived = page.getByTestId(`ai-archived-${id}`)
  await expect(archived).toContainText("Playwright agent chat")
  await page.getByTestId(`ai-restore-${id}`).click()
  await expect(archived).toHaveCount(0)
  await expect(row).toBeVisible()

  // Still pinned, so its row shows its buttons without being pointed at.
  await page.getByTestId(`ai-archive-${id}`).click()
  await expect(archived).toBeVisible()
  await page.getByTestId(`ai-delete-${id}`).click()
  await page.getByRole("dialog", { name: "Delete chat?" }).getByRole("button", { name: "Delete" }).click()
  await expect(archived).toHaveCount(0)
})
