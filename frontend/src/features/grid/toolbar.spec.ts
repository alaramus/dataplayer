import { describe, expect, it } from "vitest"

import { NOT_OFFERED, NOT_YET, reasonFor, tipOf, TOOLBAR_GROUPS } from "./toolbar"

describe("what a command in the row says", () => {
  it("says only its name while it can be used", () => {
    expect(tipOf("Download", null)).toBe("Download")
  })

  it("says its name and the reason otherwise, in that order", () => {
    // The name first, because a person hovering a button is asking what it is
    // before asking why it is grey.
    expect(tipOf("Download", NOT_OFFERED.download)).toBe(
      "Download — this source does not write rows out"
    )
  })
})

describe("which of the two reasons is given", () => {
  it("is what the source will never do, over what is merely missing now", () => {
    // "Tick a row" under a button that will never delete anything is a lie,
    // and the lie is worse than the vaguer truth.
    expect(reasonFor(false, NOT_OFFERED.remove, NOT_YET.noRowsPicked)).toBe(
      NOT_OFFERED.remove
    )
  })

  it("is what is missing now, once the source can do the thing at all", () => {
    expect(reasonFor(true, NOT_OFFERED.remove, NOT_YET.noRowsPicked)).toBe(
      NOT_YET.noRowsPicked
    )
  })

  it("is nothing at all when there is nothing in the way", () => {
    expect(reasonFor(true, NOT_OFFERED.remove)).toBeNull()
  })
})

describe("the groups of the row", () => {
  it("run from what only looks to what writes, and end with the tab's own", () => {
    // The order is the order of a working session, and it puts everything
    // that writes together and apart from everything that reads.
    expect(TOOLBAR_GROUPS.map((group) => group.name)).toEqual([
      "view",
      "open",
      "out",
      "write",
      "tab",
    ])
  })

  it("are named in words about the rows, not about the application", () => {
    expect(TOOLBAR_GROUPS.map((group) => group.label)).toEqual([
      "The view",
      "Read it as",
      "Take it out",
      "Change the rows",
      "This tab",
    ])
  })
})
