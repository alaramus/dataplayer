import { describe, expect, it } from "vitest"

import type { PasteOffer } from "@/client"
import { chosenOffer, firstStep, holdLines, pasteHint } from "./pasteOffers"

const copying: PasteOffer = { kind: "file_copy", title: "Copy files", available: true }
const saving: PasteOffer = {
  kind: "relation_csv",
  title: "Save as CSV",
  available: true,
  converts: true,
  suggested_name: "people.csv",
}

describe("choosing what Paste runs", () => {
  it("runs an available offer, or one held back only by a taken name", () => {
    const taken = { ...copying, available: false, name_conflict: true }

    expect(chosenOffer([copying])).toBe(copying)
    expect(chosenOffer([taken])).toBe(taken)
    expect(chosenOffer([{ ...copying, available: false, reason: "No" }])).toBeNull()
    expect(chosenOffer([])).toBeNull()
  })

  it("says why Paste is off, in the order the reader can act on", () => {
    const refused = { ...copying, available: false, reason: "Copy files, not folders or links" }
    const base = { places: 1, checking: false, failed: false }

    expect(pasteHint({ ...base, places: 2, offers: [copying] })).toBe("Choose one destination folder")
    expect(pasteHint({ ...base, checking: true, offers: undefined })).toBe("Checking what can be pasted here")
    expect(pasteHint({ ...base, failed: true, offers: undefined })).toBe("Could not check this destination")
    expect(pasteHint({ ...base, offers: [refused] })).toBe("Copy files, not folders or links")
    expect(pasteHint({ ...base, offers: [] })).toBe("Nothing here can take what was copied")
    expect(pasteHint({ ...base, offers: [copying] })).toBeUndefined()
  })

  it("never runs a conversion straight from the menu", () => {
    expect(firstStep(saving)).toBe("name")
    expect(firstStep({ ...saving, name_conflict: true })).toBe("name")
    expect(firstStep({ ...copying, available: false, name_conflict: true })).toBe("conflict")
    expect(firstStep(copying)).toBe("run")
  })
})

describe("whether Copy and Cut are drawn", () => {
  it("lets a source with its own Paste hold whatever is ticked", () => {
    expect(holdLines(true, 2, undefined)).toEqual({
      copy: { enabled: true },
      cut: { enabled: true },
    })
    expect(holdLines(true, 0, undefined).copy).toEqual({
      enabled: false,
      reason: "Tick a row to use this",
    })
  })

  it("draws for any other source only what the server says something could take", () => {
    expect(holdLines(false, 1, { can_copy: { available: true }, can_cut: null })).toEqual({
      copy: { enabled: true },
    })
    expect(
      holdLines(false, 2, {
        can_copy: { available: false, reason: "Copy one table at a time" },
        can_cut: null,
      })
    ).toEqual({ copy: { enabled: false, reason: "Copy one table at a time" } })
    expect(holdLines(false, 1, { can_copy: null, can_cut: null })).toEqual({})
  })

  it("draws nothing before the server has answered", () => {
    expect(holdLines(false, 1, undefined)).toEqual({})
  })
})
