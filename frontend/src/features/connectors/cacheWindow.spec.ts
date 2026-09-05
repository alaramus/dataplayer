import { describe, expect, it } from "vitest"

import {
  SOURCE_WINDOW,
  cacheWindowNote,
  cacheWindowOf,
  cacheWindowOptions,
  cacheWindowValue,
  sourceWindowLabel,
  windowApplies,
} from "./cacheWindow"

const POSTGRES = { catalog: 30, fetch: 10 }

describe("the window a connection is given in the form", () => {
  it("keeps leaving it to the source apart from keeping nothing", () => {
    // Two different answers, and a select that held null for the first would
    // have to spell the second as a number that means something else.
    expect(cacheWindowValue(null)).toBe(SOURCE_WINDOW)
    expect(cacheWindowValue(undefined)).toBe(SOURCE_WINDOW)
    expect(cacheWindowValue(0)).toBe(0)
    expect(cacheWindowOf(SOURCE_WINDOW)).toBeNull()
    expect(cacheWindowOf(0)).toBe(0)
  })

  it("reports nothing for a value that was never offered", () => {
    // Undefined rather than null: a select answering something unreadable
    // must not quietly hand the window back to the source and be saved.
    expect(cacheWindowOf(7)).toBeUndefined()
    expect(cacheWindowOf("300")).toBeUndefined()
    expect(cacheWindowOf(null)).toBeUndefined()
  })

  it("offers every value it can read back", () => {
    for (const option of cacheWindowOptions(POSTGRES)) {
      expect(cacheWindowOf(option.value)).not.toBeUndefined()
    }
  })
})

describe("what the source's own choice is called", () => {
  it("says the durations rather than naming a policy", () => {
    // "As the source decides" tells somebody who has never seen the inside of
    // this application nothing at all; the numbers are the whole point (D105).
    expect(sourceWindowLabel(POSTGRES)).toBe(
      "As this source decides (rows 10s, lists 30s)"
    )
    expect(cacheWindowNote(null, POSTGRES)).toBe(
      "Rows are re-read after 10s and catalog levels after 30s."
    )
  })

  it("says a source that keeps nothing is always read live", () => {
    // Null is not zero: nothing here would change it, so the field says so
    // and the screen switches it off.
    expect(windowApplies(null)).toBe(false)
    expect(sourceWindowLabel(null)).toBe("This source is always read live")
    expect(cacheWindowNote(300, null)).toContain("whatever is chosen here")
  })

  it("falls back to words while the source types are still loading", () => {
    expect(windowApplies(undefined)).toBe(true)
    expect(sourceWindowLabel(undefined)).toBe("As this source decides")
    expect(cacheWindowNote(null, undefined)).toContain("as long as this source says")
  })

  it("says what a chosen duration does", () => {
    expect(cacheWindowNote(0, POSTGRES)).toBe("Every read reaches the source.")
    expect(cacheWindowNote(300, POSTGRES)).toBe(
      "Rows and catalog levels are re-read after 5m."
    )
  })
})
