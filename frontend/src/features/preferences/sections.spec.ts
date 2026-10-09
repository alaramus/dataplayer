import { describe, expect, it } from "vitest"

import { sectionOf } from "@/shared/ui"

import { PREFERENCE_SECTIONS } from "./sections"

describe("what Preferences is made of", () => {
  it("names each section once, and each one says what it is for", () => {
    const ids = PREFERENCE_SECTIONS.map((section) => section.id)

    expect(new Set(ids).size).toBe(ids.length)
    expect(PREFERENCE_SECTIONS.every((section) => section.summary.length > 0)).toBe(true)
  })

  it("opens the first section for an address that names none, and the one it names", () => {
    expect(sectionOf(PREFERENCE_SECTIONS, undefined).id).toBe("general")
    expect(sectionOf(PREFERENCE_SECTIONS, "nothing-of-ours").id).toBe("general")
    expect(sectionOf(PREFERENCE_SECTIONS, "ssh-keys").id).toBe("ssh-keys")
  })
})
