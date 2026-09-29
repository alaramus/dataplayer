import { describe, expect, it } from "vitest"

import { railEntry } from "./railEntry"

describe("a dashboard in the rail", () => {
  it("stands on the current tab's ground while open when it has no colour", () => {
    expect(railEntry(null, true)).toEqual({ variant: "quiet", current: true, tinted: false, filled: false })
    expect(railEntry(undefined, false)).toEqual({ variant: "quiet", current: false, tinted: false, filled: false })
  })

  it("is washed in its colour while closed and filled with it while open", () => {
    expect(railEntry("#1e88e5", false)).toEqual({ variant: "quiet", current: false, tinted: true, filled: false })
    expect(railEntry("#1E88E5", true)).toEqual({ variant: "quiet", current: false, tinted: false, filled: true })
  })

  it("treats what is not a colour as none", () => {
    expect(railEntry("blue", true).current).toBe(true)
  })
})
