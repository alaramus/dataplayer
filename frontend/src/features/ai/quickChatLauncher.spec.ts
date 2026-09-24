import { describe, expect, it, vi } from "vitest"

import type { QuickChatSummary } from "@/client"

import { explainRequest, openQuickChat, quickChatIntent, quoteSelection, reusableEmptyQuickChat } from "./quickChatLauncher"

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

  it("quotes selected lines in the immediate explanation request", () => {
    expect(quoteSelection("one\ntwo")).toBe("> one\n> two")
    expect(explainRequest("one\ntwo")).toBe(
      "Explain in more detail: one two\n\n> one\n> two"
    )
  })

  it("reuses an empty quick chat from history even when another chat was selected", async () => {
    const chats = [
      { id: "used", title: "New quick chat" },
      { id: "named", title: "Research" },
      { id: "empty", title: "New quick chat" },
    ] as QuickChatSummary[]
    const read = vi.fn(async (id: string) => ({ messages: id === "used" ? ["hello"] : [] }))
    expect(await reusableEmptyQuickChat(chats, read)).toBe("empty")
    expect(read.mock.calls.map(([id]) => id)).toEqual(["used", "empty"])
    expect(await reusableEmptyQuickChat([], read)).toBeNull()
  })
})
