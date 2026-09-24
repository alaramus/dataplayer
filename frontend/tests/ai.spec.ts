import { expect, test } from "@playwright/test"

import { openNode, pickSchema } from "./utils/catalog"
import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { chooseTheme } from "./utils/theme"
import { deleteConnector, openConnector } from "./utils/workspace"

test("keeps unsent text when leaving and returning to the AI space", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-ai").click()
  await page.getByTestId("ai-new-chat").click()
  const input = page.getByTestId("ai-message-input")
  await expect(input).toBeVisible()
  await input.fill("A question I have not sent")

  await page.getByTestId("space-data").click()
  await page.getByTestId("space-ai").click()

  await expect(page.getByTestId("ai-message-input")).toHaveValue("A question I have not sent")
})

test("attaches named workspace tabs without overflowing a narrow composer", async ({ page }) => {
  const name = `e2e-ai-context-${Date.now()}`
  await login(page)
  await chooseTheme(page, "dark")
  await createPostgresConnector(page, name)
  await openConnector(page, name)
  await pickSchema(page, "pg_catalog")
  await openNode(page, "pg_class")

  await page.getByTestId("space-ai").click()
  // The composer exists once a chat is open; on an empty history the space is
  // a welcome screen, so the chat is made here rather than presumed.
  await page.getByTestId("ai-new-chat").click()
  await expect(page.getByTestId("ai-new-chat")).toBeEnabled()
  await page.getByTestId("ai-attach").click()
  await page.getByTestId("menu-item-tabs").click()
  const dialog = page.getByTestId("ai-context-dialog")
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole("checkbox", { name: `${name} · Catalog`, exact: true })).toBeVisible()
  await expect(dialog.getByRole("checkbox", { name: `${name} · pg_class · Rows`, exact: true })).toBeVisible()

  await page.setViewportSize({ width: 420, height: 760 })
  const dialogBox = await dialog.boundingBox()
  expect(dialogBox).not.toBeNull()
  expect(dialogBox!.x).toBeGreaterThanOrEqual(0)
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(420)
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

  await dialog.getByRole("checkbox", { name: `${name} · Catalog`, exact: true }).click()
  await dialog.getByRole("checkbox", { name: `${name} · pg_class · Rows`, exact: true }).click()
  await dialog.getByRole("button", { name: "Done", exact: true }).click()
  const contexts = page.getByLabel("Tabs attached to the next message")
  await expect(contexts).toContainText(`${name} · Catalog`)
  await expect(contexts).toContainText(`${name} · pg_class · Rows`)
  expect(await contexts.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)

  await page.getByRole("button", { name: `Remove ${name} · Catalog`, exact: true }).click()
  await expect(contexts).not.toContainText(`${name} · Catalog`)
  await page.getByTestId("space-data").click()
  await page.setViewportSize({ width: 1280, height: 720 })
  await deleteConnector(page, name)
})

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

  const active = page.locator('[data-testid^="ai-chat-row-"][data-active="true"]')
  await page.getByTestId("ai-new-chat").click()
  await expect(page.getByTestId("ai-new-chat")).toBeEnabled()
  // An untouched New chat may be reused, so the active row need not change.
  await expect(active).toBeVisible()
  const conversationId = (await active.getAttribute("data-testid"))?.replace("ai-chat-row-", "")
  expect(conversationId).toBeTruthy()
  const chatCount = await page.locator('[data-testid^="ai-chat-row-"]').count()
  await page.getByTestId("ai-new-chat").click()
  await expect(active).toHaveAttribute("data-testid", `ai-chat-row-${conversationId}`)
  await expect(page.locator('[data-testid^="ai-chat-row-"]')).toHaveCount(chatCount)

  // Collapsed, the rail keeps a head with the plus alone in it, on the strip
  // the open chat's head stands on; Settings stays at its foot.
  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId("ai-history")).toHaveCount(0)
  const railHead = page.getByTestId("ai-rail-head")
  const chatHead = page.getByTestId("ai-chat-head")
  await expect(railHead.getByRole("button")).toHaveCount(1)
  await expect(railHead.getByTestId("ai-new-chat")).toHaveAttribute("aria-label", "New chat")
  await expect(page.getByTestId("ai-new-project")).toHaveCount(0)
  await expect(railHead).toHaveCSS(
    "background-color",
    await chatHead.evaluate((element) => getComputedStyle(element).backgroundColor)
  )
  const bottomOf = async (testId: string) => {
    const box = await page.getByTestId(testId).boundingBox()
    return Math.round((box?.y ?? 0) + (box?.height ?? 0))
  }
  expect(await bottomOf("ai-rail-head")).toBe(await bottomOf("ai-chat-head"))
  await expect(page.getByTestId("ai-open-settings")).toHaveAttribute("aria-label", "Settings")
  expect(await bottomOf("ai-rail") - await bottomOf("ai-open-settings")).toBeLessThan(24)
  await page.getByTestId("app-toggle-first-panel").click()
  await expect(page.getByTestId("ai-history")).toBeVisible()

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

  await page.getByTestId("ai-filter-open").click()
  const chatFilter = page.getByTestId("ai-name-filter")
  await expect(chatFilter).toBeFocused()
  await expect(page.getByTestId("ai-new-chat")).toHaveCount(0)
  await chatFilter.fill("PLAYWRIGHT AGENT CHAT")
  await expect(active).toBeVisible()
  await chatFilter.fill("no chat has this name")
  await expect(active).toHaveCount(0)
  await expect(page.getByTestId("ai-history")).toContainText("No matching chats or projects")
  await chatFilter.press("Escape")
  await expect(page.getByTestId("ai-new-chat")).toBeVisible()
  await expect(active).toBeVisible()

  // The composer follows what is typed and then stops: no corner grip to drag,
  // and a long draft never squeezes the transcript off the card.
  const composer = page.getByTestId("ai-message-input")
  await expect(composer).toHaveCSS("resize", "none")
  await composer.fill("word ".repeat(400))
  expect((await composer.boundingBox())?.height).toBeLessThanOrEqual(150)
  await expect(page.getByTestId("ai-messages")).toBeVisible()
  await composer.fill("")

  // The model is chosen in the chat itself and stays with it, and it is what
  // the next chat starts with: the settings show it too.
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

  // Files travel with a message beside the tabs (D142). An image shows itself,
  // and one the chosen model cannot read holds the message back until it goes.
  await page.getByTestId("ai-attach").click()
  await expect(page.getByTestId("menu-item-files")).toBeVisible()
  await page.keyboard.press("Escape")
  await page.getByTestId("ai-file-input").setInputFiles([
    { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("Order 42 shipped late.\n") },
    {
      name: "dot.png",
      mimeType: "image/png",
      buffer: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
        "base64"
      ),
    },
  ])
  const files = page.getByTestId("ai-file-chip")
  await expect(files).toHaveCount(2)
  await expect(files.nth(1).locator("img")).toBeVisible()
  await expect(page.getByTestId("ai-send")).toBeEnabled()
  await page.getByTestId("ai-chat-model").click()
  await page.getByRole("option", { name: /DeepSeek V4 Flash/ }).click()
  await expect(files.nth(1)).toContainText("DeepSeek V4 Flash does not read images")
  await expect(page.getByTestId("ai-send")).toBeDisabled()
  await page.getByRole("button", { name: "Remove dot.png" }).click()
  await expect(page.getByTestId("ai-send")).toBeEnabled()
  await page.getByRole("button", { name: "Remove notes.md" }).click()
  await expect(files).toHaveCount(0)
  await page.getByTestId("ai-chat-model").click()
  await page.getByRole("option", { name: /Claude Opus 5/ }).click()
  await expect(page.getByTestId("ai-chat-model")).toContainText("Claude Opus 5")

  // What the agent may change belongs to the chat too, and read only is the
  // narrow end of the three.
  await page.getByTestId("ai-chat-policy").click()
  await page.getByRole("option", { name: /Read only/ }).click()
  await expect(page.getByTestId("ai-chat-policy")).toContainText("Read only")
  // The settings' switch for every chat is offered there too, and choosing it
  // is turning that switch on.
  await page.getByTestId("ai-chat-policy").click()
  await page.getByRole("option", { name: /Allow all changes in every chat/ }).click()
  await expect(page.getByTestId("ai-chat-policy")).toContainText("Allow all changes in every chat")
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
  await expect(page.getByTestId("ai-model")).toContainText("Claude Opus 5")
  await expect(page.getByTestId("ai-allow-all")).toHaveAttribute("aria-checked", "true")
  await page.getByTestId("ai-allow-all").click()
  await expect(page.getByTestId("ai-allow-all")).toHaveAttribute("aria-checked", "false")

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
  // Read only gave way when every chat was allowed from here.
  await expect(page.getByTestId("ai-chat-policy")).toContainText("Ask before changes")
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
  // Offered a name, focused, so Create alone makes a project.
  await expect(page.getByTestId("ai-project-name")).toHaveValue(/^New project( \d+)?$/)
  await expect(page.getByTestId("ai-project-name")).toBeFocused()
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
