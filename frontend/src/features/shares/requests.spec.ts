import { describe, expect, it } from "vitest"

import { isRequestEvent, wordingOf } from "./requests"
import type { AccessRequestEvent } from "./requests"

const asked: AccessRequestEvent = {
  kind: "asked",
  request_id: "r1",
  connector_id: "c1",
  connector_label: "prod-db",
  person: "ivan@example.com",
}

describe("what an event says", () => {
  it("names who is waiting and on what", () => {
    expect(wordingOf(asked)).toBe(
      "ivan@example.com is asking for access to prod-db"
    )
  })

  it("names the level that was given", () => {
    expect(
      wordingOf({ ...asked, kind: "answered", outcome: "approved", access: "write" })
    ).toBe("ivan@example.com gave you write access to prod-db")
  })

  it("says a refusal without a reason", () => {
    // D61: the reason is a conversation between people, not a field in a form,
    // so there is none to word.
    expect(wordingOf({ ...asked, kind: "answered", outcome: "declined" })).toBe(
      "ivan@example.com did not open access to prod-db"
    )
  })

  it("falls back to the level an ask is always for", () => {
    expect(wordingOf({ ...asked, kind: "answered", outcome: "approved" })).toContain(
      "read access"
    )
  })
})

describe("what arrives on the socket", () => {
  it("is taken only when it has the shape of an event", () => {
    expect(isRequestEvent(asked)).toBe(true)
    expect(isRequestEvent({ kind: "asked" })).toBe(false)
    expect(isRequestEvent(null)).toBe(false)
    expect(isRequestEvent("asked")).toBe(false)
  })
})
