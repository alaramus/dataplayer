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

  // The key beside a model offered in the chat opens the same key window the
  // settings do; it used to do nothing at all there.
  await page.getByTestId("ai-chat-model").click()
  await page.getByRole("button", { name: /Manage .* API key/ }).first().click()
  await expect(page.getByTestId("ai-key-dialog")).toBeVisible()
  await page.getByTestId("ai-key-dialog").getByRole("button", { name: "Close" }).click()

  // What the agent may change belongs to the chat too, and read only is the
  // narrow end of the three.
  await page.getByTestId("ai-chat-policy").click()
  await page.getByRole("option", { name: /Read only/ }).click()
  await expect(page.getByTestId("ai-chat-policy")).toContainText("Read only")
  // Speaking the message is offered beside it; whether this browser can listen
  // is its own answer, and the tooltip carries it either way.
  await expect(page.getByTestId("ai-dictate")).toBeVisible()

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

  // The entry is a switch: pressing it again comes back to the chat it left.
  await expect(page.getByTestId("ai-open-settings")).toHaveAttribute("aria-pressed", "true")
  await page.getByTestId("ai-open-settings").click()
  await expect(page.getByTestId("ai-settings")).toHaveCount(0)
  await expect(page.getByTestId("ai-messages")).toBeVisible()
  await expect(page.getByTestId(`ai-chat-row-${conversationId ?? ""}`)).toHaveAttribute(
    "data-active", "true"
  )

  // A chat is pinned above the rest and archived out of the history from its
  // row; it is deleted only from the archive, in the settings.
  const id = conversationId ?? ""
  const row = page.getByTestId(`ai-chat-row-${id}`)
  // Its buttons are the pointer's: a chat clicked and left carries none.
  await page.getByTestId(`ai-chat-${id}`).click()
  await page.getByTestId("ai-messages").hover()
  await expect(page.getByTestId(`ai-pin-${id}`)).toBeHidden()
  await row.hover()
  await page.getByTestId(`ai-pin-${id}`).click()
  await expect(page.locator('[data-testid^="ai-chat-row-"]').first()).toHaveAttribute(
    "data-testid", `ai-chat-row-${id}`
  )
  // A project is a folder and nothing else: the chat moves into it, hides with
  // it, and outlives it.
  await page.getByTestId("ai-new-project").click()
  await page.getByTestId("ai-project-name").fill("Playwright project")
  await page.getByTestId("ai-project-save").click()
  const toggle = page
    .locator('[data-testid^="ai-project-toggle-"]')
    .filter({ hasText: "Playwright project" })
  await expect(toggle).toBeVisible()
  const projectId = ((await toggle.getAttribute("data-testid")) ?? "").replace(
    "ai-project-toggle-", ""
  )

  await row.hover()
  await page.getByTestId(`ai-move-${id}`).click()
  await page.locator('[data-testid^="menu-item-"]').filter({ hasText: "Playwright project" }).click()
  await expect(page.getByTestId(`ai-project-${projectId}`).getByTestId(`ai-chat-row-${id}`)).toBeVisible()

  await toggle.click()
  await expect(row).toHaveCount(0)
  await toggle.click()
  await expect(row).toBeVisible()

  await toggle.hover()
  await page.getByTestId(`ai-project-delete-${projectId}`).click()
  await page.getByRole("dialog", { name: "Delete project?" }).getByRole("button", { name: "Delete" }).click()
  await expect(toggle).toHaveCount(0)
  await expect(row).toBeVisible()

  await row.hover()
  await page.getByTestId(`ai-archive-${id}`).click()
  await expect(row).toHaveCount(0)

  await page.getByTestId("ai-open-settings").click()
  const archived = page.getByTestId(`ai-archived-${id}`)
  await expect(archived).toContainText("Playwright agent chat")
  await page.getByTestId(`ai-restore-${id}`).click()
  await expect(archived).toHaveCount(0)
  await expect(row).toBeVisible()

  await row.hover()
  await page.getByTestId(`ai-archive-${id}`).click()
  await expect(archived).toBeVisible()
  await page.getByTestId(`ai-delete-${id}`).click()
  await page.getByRole("dialog", { name: "Delete chat?" }).getByRole("button", { name: "Delete" }).click()
  await expect(archived).toHaveCount(0)
})
