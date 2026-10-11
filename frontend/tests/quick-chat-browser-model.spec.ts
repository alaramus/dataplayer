import { expect, test } from "@playwright/test"

import { login } from "./utils/login"

/**
 * The model Chrome runs on this computer (D223), stood in for by a page-side
 * fake: the real one needs gigabytes and a capable graphics card.
 */
test("the quick chat downloads the browser's model and keeps its answer in the history", async ({ page }) => {
  await page.addInitScript(() => {
    let state = "downloadable"
    const asked: unknown[] = []
    Object.assign(window, { __nanoAsked: asked })
    Object.assign(window, {
      LanguageModel: {
        availability: async () => state,
        create: async (options?: {
          initialPrompts?: unknown[]
          monitor?: (monitor: { addEventListener: (type: string, listener: (event: { loaded: number }) => void) => void }) => void
        }) => {
          options?.monitor?.({ addEventListener: (_type, listener) => { listener({ loaded: 0.5 }); listener({ loaded: 1 }) } })
          state = "available"
          asked.push(options?.initialPrompts ?? [])
          return {
            async *promptStreaming(question: string) { yield "Nano says: "; yield question },
            destroy: () => {},
          }
        },
      },
    })
  })
  await login(page)
  await page.getByTestId("quick-chat-rail").click()
  const chat = page.getByTestId("quick-chat-window")
  await expect(chat).toBeVisible()

  await chat.getByRole("combobox").click()
  await page.getByRole("listbox").getByRole("option", { name: /Gemini Nano/ }).click()
  const offer = page.getByTestId("quick-chat-browser-model")
  await expect(offer).toContainText("Chrome downloads it once")
  await page.getByTestId("quick-chat-input").fill("Is it local?")
  await expect(page.getByTestId("quick-chat-send")).toBeDisabled()
  await chat.screenshot({ path: "test-results/quick-chat-browser-model.png" })

  await page.getByTestId("quick-chat-browser-download").click()
  await expect(offer).toHaveCount(0)
  await page.getByTestId("quick-chat-send").click()
  const messages = page.getByTestId("quick-chat-messages")
  await expect(messages).toContainText("Nano says: Is it local?")

  // The question and the answer are the server's, in the history every quick
  // chat shares, and the browser's model was given the server's instructions.
  await page.getByRole("button", { name: "Close window" }).click()
  await page.getByTestId("space-ai").click()
  await page.getByText("Is it local?", { exact: true }).first().click()
  await expect(page.getByTestId("quick-chat-messages")).toContainText("Nano says: Is it local?")
  const prompts = await page.evaluate(() => (window as unknown as { __nanoAsked: { role: string }[][] }).__nanoAsked)
  expect(prompts.at(-1)?.[0]?.role).toBe("system")
})

test("an answer the browser's model is writing can be stopped, and what it wrote is kept", async ({ page }) => {
  await page.addInitScript(() => {
    Object.assign(window, {
      LanguageModel: {
        availability: async () => "available",
        create: async () => ({
          // Writes once, then goes on until it is stopped, as a long answer does.
          async *promptStreaming(_question: string, options?: { signal?: AbortSignal }) {
            yield "Written before the stop"
            await new Promise((_resolve, reject) => {
              options?.signal?.addEventListener("abort", () => reject(new DOMException("Stopped", "AbortError")))
            })
          },
          destroy: () => {},
        }),
      },
    })
  })
  await login(page)
  await page.getByTestId("quick-chat-rail").click()
  const chat = page.getByTestId("quick-chat-window")
  await chat.getByRole("combobox").click()
  await page.getByRole("listbox").getByRole("option", { name: /Gemini Nano/ }).click()
  const question = `Stop me ${Date.now()}`
  await page.getByTestId("quick-chat-input").fill(question)
  await page.getByTestId("quick-chat-send").click()
  const messages = page.getByTestId("quick-chat-messages")
  await expect(messages).toContainText("Written before the stop")

  await page.getByTestId("quick-chat-stop").click()
  await expect(page.getByTestId("quick-chat-stop")).toHaveCount(0)
  await expect(page.getByTestId("quick-chat-send")).toBeVisible()
  await expect(page.getByTestId("quick-chat-answering")).toHaveCount(0)
  await expect(messages).toContainText("Written before the stop")

  await page.getByRole("button", { name: "Close window" }).click()
  await page.getByTestId("space-ai").click()
  await page.getByText(question, { exact: true }).first().click()
  await expect(page.getByTestId("quick-chat-messages")).toContainText("Written before the stop")
})
