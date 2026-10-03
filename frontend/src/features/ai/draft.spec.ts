import { describe, expect, it } from "vitest"
import { effectScope } from "vue"

import { hasAiDraft, setAiDraft, useAiDraft } from "./draft"

describe("unsent agent text", () => {
  it("survives reopening the same chat without mixing chats", () => {
    const firstScope = effectScope()
    const first = firstScope.run(() => useAiDraft("draft-test-first"))!
    first.value = "A question in progress"
    firstScope.stop()
    expect(useAiDraft("draft-test-second").value).toBe("")
    const reopened = useAiDraft("draft-test-first")
    expect(reopened.value).toBe("A question in progress")
    reopened.value = ""
  })

  it("forgets text when it is cleared for sending", () => {
    const draft = useAiDraft("draft-test-sent")
    expect(hasAiDraft("draft-test-sent")).toBe(false)
    draft.value = "Send this"
    expect(hasAiDraft("draft-test-sent")).toBe(true)
    draft.value = ""
    expect(hasAiDraft("draft-test-sent")).toBe(false)
    expect(useAiDraft("draft-test-sent").value).toBe("")
  })
})

describe("words handed to a composer before it mounts", () => {
  it("are what the composer finds, and an empty text clears them", () => {
    setAiDraft("draft-test-handed", "find the orders table")
    expect(useAiDraft("draft-test-handed").value).toBe("find the orders table")
    setAiDraft("draft-test-handed", "")
    expect(hasAiDraft("draft-test-handed")).toBe(false)
  })
})
