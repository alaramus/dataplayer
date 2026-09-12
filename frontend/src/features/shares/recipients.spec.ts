import { describe, expect, it } from "vitest"

import { emptyRecipientsMessage } from "./recipients"

describe("an empty recipient picker", () => {
  it("explains that an administrator must make another active account available", () => {
    expect(emptyRecipientsMessage(0, 0)).toBe(
      "No other active accounts are available. Ask an administrator to create or enable an account, then reopen Share."
    )
  })

  it("directs the owner to existing grants when everybody already has access", () => {
    expect(emptyRecipientsMessage(2, 0)).toBe(
      "All other active accounts already have access. Change their access levels in the connection's Permissions tab."
    )
  })

  it("shows no empty-state guidance when a recipient can be selected", () => {
    expect(emptyRecipientsMessage(2, 1)).toBe("")
  })
})
