import { afterEach, describe, expect, it } from "vitest"

import {
  BROWSER_MODEL_KEY,
  answerInBrowser,
  browserModelOptions,
  readBrowserModelState,
  shorterHistory,
} from "./browserModel"

type Prompt = { role: string; content: string }

function installModel(options: { fits: number; pieces: string[]; state?: string }) {
  const made: Prompt[][] = []
  let destroyed = 0
  ;(globalThis as Record<string, unknown>).LanguageModel = {
    availability: async () => options.state ?? "available",
    create: async (create?: { initialPrompts?: Prompt[] }) => {
      const prompts = create?.initialPrompts ?? []
      if (prompts.length > options.fits) throw new Error("QuotaExceededError")
      made.push(prompts)
      return {
        async *promptStreaming() { yield* options.pieces },
        destroy: () => { destroyed += 1 },
      }
    },
  }
  return { made, destroyed: () => destroyed }
}

afterEach(() => { delete (globalThis as Record<string, unknown>).LanguageModel })

describe("the browser's model", () => {
  it("is unsupported where the browser has no Prompt API", async () => {
    expect(await readBrowserModelState()).toBe("unsupported")
    installModel({ fits: 10, pieces: [], state: "downloadable" })
    expect(await readBrowserModelState()).toBe("downloadable")
  })

  it("can be chosen only where it can run", () => {
    const row = (state: Parameters<typeof browserModelOptions>[0]) =>
      browserModelOptions(state).find((one) => one.value === BROWSER_MODEL_KEY)
    expect(row("unsupported")?.disable).toBe(true)
    expect(row("unavailable")?.disable).toBe(true)
    expect(row("downloadable")?.disable).toBe(false)
    expect(row("available")?.disable).toBe(false)
    expect(browserModelOptions("available")[0]?.group).toBe(true)
  })

  it("drops the older half of the turns and keeps the instructions", () => {
    const history = [
      { role: "system" as const, content: "rules" },
      { role: "user" as const, content: "1" }, { role: "assistant" as const, content: "2" },
      { role: "user" as const, content: "3" }, { role: "assistant" as const, content: "4" },
    ]
    expect(shorterHistory(history).map((one) => one.content)).toEqual(["rules", "3", "4"])
  })

  it("answers with a history shortened until it fits, streaming as it writes", async () => {
    const model = installModel({ fits: 3, pieces: ["Hel", "lo"] })
    const heard: string[] = []

    const answer = await answerInBrowser({
      prompt: "rules",
      history: [
        { role: "user", content: "1" }, { role: "assistant", content: "2" },
        { role: "user", content: "3" }, { role: "assistant", content: "4" },
      ],
      question: "5",
      onText: (piece) => heard.push(piece),
    })

    expect(answer).toBe("Hello")
    expect(heard).toEqual(["Hel", "lo"])
    expect(model.made[0]?.map((one) => one.content)).toEqual(["rules", "3", "4"])
    expect(model.destroyed()).toBe(1)
  })

  it("gives up when not even the instructions fit", async () => {
    installModel({ fits: 0, pieces: [] })
    await expect(answerInBrowser({ prompt: "rules", history: [], question: "?", onText: () => {} }))
      .rejects.toThrow("QuotaExceededError")
  })
})
