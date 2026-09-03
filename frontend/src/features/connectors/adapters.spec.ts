import { describe, expect, it } from "vitest"

import { adapterIcon, categoryIcon, UNKNOWN_CATEGORY_ICON, UNKNOWN_ADAPTER_ICON } from "./adapters"

describe("the icon of a source type", () => {
  it("tells the two types apart", () => {
    expect(adapterIcon("postgres")).not.toBe(adapterIcon("file"))
  })

  it("names a file under the icons served with the app", () => {
    expect(adapterIcon("postgres")).toBe("img:/icons/services/postgresql.svg")
  })

  it("falls back for a type the backend gained since this build", () => {
    expect(adapterIcon("kafka")).toBe(UNKNOWN_ADAPTER_ICON)
  })
})

describe("the glyph of a category", () => {
  it("gives each group its own", () => {
    const drawn = ["sql", "keyvalue", "files"].map(categoryIcon)
    expect(new Set(drawn).size).toBe(drawn.length)
  })

  it("falls back for a group the backend gained since this build", () => {
    expect(categoryIcon("timeseries")).toBe(UNKNOWN_CATEGORY_ICON)
  })
})
