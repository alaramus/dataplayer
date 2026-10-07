import { describe, expect, it } from "vitest"

import { plainSpeechText } from "./speechText"

describe("speech text", () => {
  it("removes code and Markdown marks from speech", () => {
    expect(plainSpeechText("**Hello** [there](https://example.test)\n```sql\nsecret\n```"))
      .toBe("Hello there")
  })

  it("strips code marks too, so plain sources must not go through it", () => {
    expect(plainSpeechText("SELECT * FROM orders")).toBe("SELECT FROM orders")
  })
})
