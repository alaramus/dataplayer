import { beforeEach, describe, expect, it } from "vitest"

import { rememberAiConversation, rememberedAiConversation } from "./state"

describe("AI space state", () => {
  beforeEach(() => localStorage.clear())
  it("remembers the selected conversation", () => {
    rememberAiConversation("conversation-1")
    expect(rememberedAiConversation()).toBe("conversation-1")
    rememberAiConversation(null)
    expect(rememberedAiConversation()).toBeNull()
  })
})
