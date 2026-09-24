import { describe, expect, it, vi } from "vitest"

import type { ConversationSummary } from "@/client"

import { reusableEmptyChat } from "./emptyChat"

function chat(id: string, title = "New chat"): ConversationSummary {
  return {
    id,
    title,
    updated_at: null,
    active: false,
    waiting: false,
    pinned: false,
    archived: false,
    model_key: null,
    change_policy: "ask",
    project_id: null,
  }
}

describe("reusing an empty chat", () => {
  it("opens an existing untouched New chat", async () => {
    const read = vi.fn().mockResolvedValue({ messages: [], runs: [] })
    expect(await reusableEmptyChat([chat("one")], read)).toBe("one")
    expect(read).toHaveBeenCalledWith("one")
  })

  it("skips a chat with messages or runs and finds another empty one", async () => {
    const read = vi.fn(async (id: string) => ({
      messages: id === "sent" ? ["hello"] : [],
      runs: id === "started" ? ["run"] : [],
    }))
    expect(await reusableEmptyChat([
      chat("named", "Work"), chat("active"), chat("sent"), chat("started"), chat("empty"),
    ].map((item) => item.id === "active" ? { ...item, active: true } : item), read)).toBe("empty")
    expect(read.mock.calls.map(([id]) => id)).toEqual(["sent", "started", "empty"])
  })

  it("allows creating a chat when no untouched New chat exists", async () => {
    const read = vi.fn().mockResolvedValue({ messages: ["hello"], runs: [] })
    expect(await reusableEmptyChat([chat("named", "Work"), chat("used")], read)).toBeNull()
    expect(read).toHaveBeenCalledTimes(1)
  })
})
