import { describe, expect, it } from "vitest"

import { gainedPanels } from "./gainedPanels"

describe("what reaches the layout", () => {
  it("calls Data forward for an arrival", () => {
    expect(gainedPanels([], ["rows:c1"])).toBe(true)
    expect(gainedPanels(["catalog:c1"], ["catalog:c1", "rows:c1"])).toBe(true)
  })

  it("leaves the space alone for a closing and a reorder", () => {
    expect(gainedPanels(["rows:c1"], [])).toBe(false)
    expect(gainedPanels(["a", "b"], ["b"])).toBe(false)
    expect(gainedPanels(["a", "b"], ["b", "a"])).toBe(false)
    expect(gainedPanels([], [])).toBe(false)
  })
})
