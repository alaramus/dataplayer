import { beforeEach, describe, expect, it } from "vitest"

import { rememberAiConversation, rememberAiOpen, rememberedAiConversation, rememberedAiOpen } from "./state"

describe("AI window state", () => {
  beforeEach(() => localStorage.clear())
  it("remembers the open window and selected conversation", () => {
    rememberAiOpen(true); rememberAiConversation("conversation-1")
    expect(rememberedAiOpen()).toBe(true)
    expect(rememberedAiConversation()).toBe("conversation-1")
    rememberAiOpen(false); rememberAiConversation(null)
    expect(rememberedAiOpen()).toBe(false)
    expect(rememberedAiConversation()).toBeNull()
  })
})
