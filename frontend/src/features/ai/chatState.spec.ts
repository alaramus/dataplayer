import { describe, expect, it } from "vitest"

import type { ConversationSummary, QuickChatSummary } from "@/client"

import { chatStateOf } from "./chatState"

function agent(flags: Partial<ConversationSummary>): ConversationSummary {
  return { id: "a", title: "Chat", updated_at: null, active: false, waiting: false, ...flags }
}

describe("chatStateOf", () => {
  it("is idle for a chat with nothing running and nothing failed", () => {
    expect(chatStateOf(agent({}))).toBe("idle")
  })

  it("is working while an answer is being written", () => {
    expect(chatStateOf(agent({ active: true }))).toBe("working")
  })

  it("is waiting rather than working while a run is paused on a question", () => {
    expect(chatStateOf(agent({ active: true, waiting: true }))).toBe("waiting")
  })

  it("is failed when the latest answer failed", () => {
    expect(chatStateOf(agent({ failed: true }))).toBe("failed")
  })

  it("is always idle for a quick chat, which has no run of its own", () => {
    const quick: QuickChatSummary = {
      id: "q", title: "Quick", model_key: null, updated_at: null,
      pinned: false, archived: false, project_id: null,
    }
    expect(chatStateOf(quick)).toBe("idle")
  })
})
