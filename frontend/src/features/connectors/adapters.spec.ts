import { describe, expect, it } from "vitest"

import { adapterIcon, UNKNOWN_ADAPTER_ICON } from "./adapters"

describe("the icon of a source type", () => {
  it("tells the two types apart", () => {
    expect(adapterIcon("postgres")).not.toBe(adapterIcon("file"))
  })

  it("falls back for a type the backend gained since this build", () => {
    expect(adapterIcon("kafka")).toBe(UNKNOWN_ADAPTER_ICON)
  })
})
