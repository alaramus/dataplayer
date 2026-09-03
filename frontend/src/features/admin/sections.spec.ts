import { describe, expect, it } from "vitest"

import { ADMIN_SECTIONS, sectionFor } from "./sections"

describe("what administering this installation is made of", () => {
  it("offers accounts first", () => {
    // The order is the order of the list, and accounts are where an
    // installation starts being administered.
    expect(ADMIN_SECTIONS[0]?.id).toBe("users")
  })

  it("names each section once, and each one says what it is for", () => {
    const ids = ADMIN_SECTIONS.map((section) => section.id)

    expect(new Set(ids).size).toBe(ids.length)
    expect(ADMIN_SECTIONS.every((section) => section.summary !== "")).toBe(true)
  })

  it("opens the first section for an address that names none", () => {
    // `/admin` is what the header button goes to, and an empty screen would be
    // a page that says nothing until something else is clicked.
    expect(sectionFor(undefined).id).toBe("users")
    expect(sectionFor("").id).toBe("users")
    expect(sectionFor("nothing-of-ours").id).toBe("users")
  })

  it("opens the section an address names", () => {
    expect(sectionFor("users").id).toBe("users")
  })
})
