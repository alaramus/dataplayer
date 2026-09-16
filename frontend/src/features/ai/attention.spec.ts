import { describe, expect, it, vi } from "vitest"

import type { ConversationSummary } from "@/client"
import { waitingItem } from "./attention"

function chat(extra: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: "chat-1",
    title: "Evening queries",
    updated_at: "2026-09-16T10:00:00Z",
    active: true,
    waiting: true,
    ...extra,
  }
}

describe("a chat where the agent waits for an answer", () => {
  it("is a warning that cannot be waved away, because the question still stands", () => {
    const item = waitingItem(chat(), () => {})

    expect(item.tone).toBe("warning")
    expect(item.dismiss).toBeNull()
    expect(item.title).toBe("The agent waits in “Evening queries”")
    expect(item.at).toBe(Date.parse("2026-09-16T10:00:00Z"))
  })

  it("opens its own chat when answered from the sheet", () => {
    const open = vi.fn()
    waitingItem(chat(), open).action?.run()

    expect(open).toHaveBeenCalledWith("chat-1")
  })

  it("falls back to now when the chat has no timestamp", () => {
    const before = Date.now()
    const item = waitingItem(chat({ updated_at: null }), () => {})

    expect(item.at).toBeGreaterThanOrEqual(before)
  })
})
