import { describe, expect, it } from "vitest"

import {
  CHECK_INTERVALS,
  checkIntervalLabel,
  checkIntervalOptions,
  checksAreOff,
} from "./checks"

describe("how often connections are checked", () => {
  it("names every choice the server offers", () => {
    const named = CHECK_INTERVALS.map(checkIntervalLabel)

    expect(named).toHaveLength(CHECK_INTERVALS.length)
    expect(named.filter((label) => label === "")).toEqual([])
    expect(new Set(named).size).toBe(named.length)
  })

  it("offers never first, because it is the answer that costs nothing", () => {
    const [first] = checkIntervalOptions()

    expect(first?.value).toBe("off")
    expect(first?.label).toContain("press check")
  })

  it("says a wait is a wait and never is not", () => {
    expect(checksAreOff("off")).toBe(true)
    expect(checksAreOff("15m")).toBe(false)
    // Before the answer has been read: nothing is known, so nothing is
    // dropped — the dots are left alone rather than cleared on every load.
    expect(checksAreOff(undefined)).toBe(false)
  })
})
