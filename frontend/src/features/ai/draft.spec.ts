import { describe, expect, it } from "vitest"
import { effectScope } from "vue"

import { useAiDraft } from "./draft"

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
    draft.value = "Send this"
    draft.value = ""
    expect(useAiDraft("draft-test-sent").value).toBe("")
  })
})
