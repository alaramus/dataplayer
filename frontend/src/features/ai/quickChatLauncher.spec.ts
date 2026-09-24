import { describe, expect, it } from "vitest"

import { explainRequest, openQuickChat, quickChatIntent, quoteSelection } from "./quickChatLauncher"

describe("quick chat opening", () => {
  it("delivers a fresh intent on every opening", () => {
    openQuickChat()
    const first = quickChatIntent.value?.id
    openQuickChat({ kind: "explain", text: "selected text" })
    expect(quickChatIntent.value?.id).not.toBe(first)
    expect(quickChatIntent.value?.request).toEqual({ kind: "explain", text: "selected text" })
  })

  it("quotes selected lines in the immediate explanation request", () => {
    expect(quoteSelection("one\ntwo")).toBe("> one\n> two")
    expect(explainRequest("one\ntwo")).toBe(
      "Explain in more detail: one two\n\n> one\n> two"
    )
  })
})
