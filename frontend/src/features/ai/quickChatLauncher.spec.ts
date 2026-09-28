import { describe, expect, it } from "vitest"

import { explainRequest, explainTitle, openQuickChat, quickChatIntent, quoteSelection } from "./quickChatLauncher"

describe("quick chat opening", () => {
  it("delivers a fresh intent on every opening", () => {
    openQuickChat()
    const first = quickChatIntent.value?.id
    openQuickChat({ kind: "explain", text: "selected text" })
    expect(quickChatIntent.value?.id).not.toBe(first)
    expect(quickChatIntent.value?.request).toEqual({ kind: "explain", text: "selected text" })
    openQuickChat({ kind: "chat", id: "saved-chat" })
    expect(quickChatIntent.value?.request).toEqual({ kind: "chat", id: "saved-chat" })
  })

  it("quotes selected lines in the immediate explanation request, once", () => {
    expect(quoteSelection("one\ntwo")).toBe("> one\n> two")
    expect(explainRequest("one\ntwo")).toBe("Explain in more detail:\n\n> one\n> two")
    // A short selection was the whole first line and the quote again.
    expect(explainRequest("MVCC").match(/MVCC/g)).toHaveLength(1)
  })

  it("names the chat by the selection, on one line and cut short", () => {
    expect(explainTitle("  one\n two ")).toBe("one two")
    const long = "x".repeat(100)
    expect(explainTitle(long)).toHaveLength(60)
    expect(explainTitle(long).endsWith("…")).toBe(true)
  })

})
