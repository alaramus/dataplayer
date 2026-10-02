import { expect, test } from "@playwright/test"

import { historyRows } from "./utils/ai"
import { login } from "./utils/login"
import { toast } from "./utils/notices"

test("opening and closing a quick chat leaves history unchanged", async ({ page }) => {
  await login(page)
  await page.getByTestId("space-ai").click()
  const rows = await historyRows(page)
  const before = await rows.count()
  await page.getByTestId("quick-chat-rail").click()
  await expect(page.getByTestId("quick-chat-window")).toBeVisible()
  // Laid out as the agent's chat is: the composer stands inside the scroller,
  // which the transcript passes under.
  await expect(page.getByTestId("quick-chat-messages").getByTestId("quick-chat-input")).toBeVisible()
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
  // Hovered before the list is read again, the row moved into the folder from
  // under the pointer and its buttons went with it.
  await expect(page.getByTestId("ai-pinned-chats").getByTestId(`ai-chat-row-${id}`)).toBeVisible()
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

test("More details asks about a selection once, and names the chat by it", async ({ page }) => {
  await login(page)
  const token = await page.evaluate(() => Object.entries(localStorage)
    .find(([key]) => key.endsWith("access_token"))?.[1])
  const server = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dataplayer:active-server:v1") ?? "null"
  ) as { url: string })
  const api = `${server.url}/api/v1/ai`
  const headers = { Authorization: `Bearer ${token ?? ""}` }
  const created = await page.request.post(`${api}/conversations`, { headers })
  expect(created.ok(), await created.text()).toBe(true)
  const conversationId = (await created.json()).id as string
  const selection = "MVCC (Multi-Version Concurrency Control)"

  // A message to select, without a model having written it.
  await page.route(`**/api/v1/ai/conversations/${conversationId}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue()
    const real = await (await route.fetch()).json()
    await route.fulfill({ json: {
      ...real,
      messages: [{ id: "m1", role: "user", content: selection, attachments: [], run_id: null, created_at: null }],
    } })
  })
  // And an answer without a provider: what matters is what is asked.
  let asked: string | null = null
  let quickChatId: string | null = null
  let answered: object | null = null
  await page.route(/\/api\/v1\/ai\/quick-chats\/[^/]+\/messages$/, async (route) => {
    asked = (route.request().postDataJSON() as { text: string }).text
    quickChatId = route.request().url().split("/").at(-2) ?? null
    answered = {
      id: quickChatId, title: selection, model_key: null, updated_at: null,
      pinned: false, archived: false, project_id: null,
      messages: [
        { id: "u1", role: "user", content: asked, created_at: null },
        { id: "a1", role: "assistant", content: "An answer.", created_at: null },
      ],
    }
    await route.fulfill({ json: answered })
  })
  // Read again after the send, it is the same answer.
  await page.route(/\/api\/v1\/ai\/quick-chats\/[^/?]+$/, async (route) => {
    const id = route.request().url().split("/").at(-1)
    if (route.request().method() === "GET" && answered !== null && id === quickChatId) {
      await route.fulfill({ json: answered })
    } else {
      await route.continue()
    }
  })

  await page.getByTestId("space-ai").click()
  await page.getByTestId(`ai-chat-${conversationId}`).click()
  const message = page.getByTestId("ai-messages").getByText(selection, { exact: true })
  // Exactly the words, as a drag across them selects them; a triple click
  // takes the paragraph break after them too.
  await message.evaluate((element) => {
    const range = document.createRange()
    range.selectNodeContents(element)
    const chosen = window.getSelection()
    chosen?.removeAllRanges()
    chosen?.addRange(range)
  })
  await message.dispatchEvent("pointerup")
  await page.getByTestId("ai-selection-menu").getByRole("button", { name: "More details" }).click()

  await expect.poll(() => asked).toBe(`Explain in more detail:\n\n> ${selection}`)
  await expect.poll(async () => {
    const chats = await (await page.request.get(`${api}/quick-chats`, { headers })).json() as { id: string; title: string }[]
    return chats.find((chat) => chat.id === quickChatId)?.title
  }).toBe(selection)

  // Copy and read aloud under each message, as in the agent's chat.
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"])
  const answer = page.getByTestId("quick-chat-messages").locator("article").filter({ hasText: "An answer." })
  await answer.hover()
  await expect(answer.getByTestId("ai-message-listen")).toBeVisible()
  await answer.getByTestId("ai-message-copy").click()
  await expect(toast(page, "Answer copied")).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("An answer.")

  await page.request.delete(`${api}/quick-chats/${quickChatId ?? ""}`, { headers })
  await page.request.delete(`${api}/conversations/${conversationId}`, { headers })
})

test("a long chat title ends in an ellipsis rather than a letter cut through", async ({ page }) => {
  await login(page)
  const token = await page.evaluate(() => Object.entries(localStorage)
    .find(([key]) => key.endsWith("access_token"))?.[1])
  const server = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("dataplayer:active-server:v1") ?? "null"
  ) as { url: string })
  const api = `${server.url}/api/v1/ai`
  const headers = { Authorization: `Bearer ${token ?? ""}` }
  const id = (await (await page.request.post(`${api}/quick-chats`, { headers })).json()).id as string
  const title = "A title far longer than the history rail has room for, whatever its width"
  await page.request.patch(`${api}/quick-chats/${id}`, { headers, data: { title } })

  await page.getByTestId("space-ai").click()
  const button = page.getByTestId(`ai-chat-${id}`)
  await expect(button).toBeVisible()
  // Whichever element holds the words is the one that must say it is cut:
  // an ellipsis on a box around it never reaches them.
  const holder = await button.evaluate((element, words) => {
    const found = [...element.querySelectorAll("*")].find((one) =>
      [...one.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent === words))
    if (!(found instanceof HTMLElement)) return null
    return { overflowing: found.scrollWidth > found.clientWidth, ellipsis: getComputedStyle(found).textOverflow }
  }, title)
  expect(holder).toEqual({ overflowing: true, ellipsis: "ellipsis" })

  await page.request.delete(`${api}/quick-chats/${id}`, { headers })
})
