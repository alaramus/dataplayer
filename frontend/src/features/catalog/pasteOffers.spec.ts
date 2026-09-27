import { describe, expect, it } from "vitest"

import type { PasteOffer } from "@/client"
import { firstStep, holdLines, offerPlace, pasteHint, pasteLines, usableOffers } from "./pasteOffers"
import type { CrossPasteIntent } from "./pasteOffers"

const copying: PasteOffer = { kind: "file_copy", title: "Copy files", available: true }
const saving: PasteOffer = {
  kind: "relation_csv",
  title: "Save as CSV",
  available: true,
  converts: true,
  workflow: "file-name",
  suggested_name: "people.csv",
}
const creating: PasteOffer = {
  kind: "rows_new_relation",
  title: "Create a table",
  available: true,
  converts: true,
  workflow: "new-relation",
}
const adding: PasteOffer = {
  kind: "rows_into_relation",
  title: "Add rows to a table",
  available: true,
  converts: true,
  workflow: "into-relation",
}

describe("choosing what Paste runs", () => {
  it("leaves adding rows to a line of its own, whatever the tick says", () => {
    const refused = { ...adding, available: false, reason: "Tick the table the rows go into" }

    expect(pasteLines([creating, adding])).toEqual({ paste: [creating], into: adding })
    expect(pasteLines([creating, refused])).toEqual({ paste: [creating], into: refused })
    expect(pasteLines([copying])).toEqual({ paste: [copying], into: null })
  })

  it("runs an available offer, or one held back only by a taken name", () => {
    const taken = { ...copying, available: false, name_conflict: true }
    const refused = { ...adding, available: false, reason: "Tick the table the rows go into" }

    expect(usableOffers([copying])).toEqual([copying])
    expect(usableOffers([taken])).toEqual([taken])
    expect(usableOffers([creating, refused])).toEqual([creating])
    expect(usableOffers([])).toEqual([])
  })

  it("says why Paste is off, in the order the reader can act on", () => {
    const refused = { ...copying, available: false, reason: "Copy files, not folders or links" }
    const base = { checking: false, failed: false }

    expect(pasteHint({ ...base, checking: true, offers: undefined })).toBe("Checking what can be pasted here")
    expect(pasteHint({ ...base, failed: true, offers: undefined })).toBe("Could not check this destination")
    expect(pasteHint({ ...base, offers: [refused] })).toBe("Copy files, not folders or links")
    expect(pasteHint({ ...base, offers: [] })).toBe("Nothing here can take what was copied")
    expect(pasteHint({ ...base, offers: [copying] })).toBeUndefined()
  })

  it("opens the window each offer names, and none for a plain copy", () => {
    expect(firstStep(saving)).toBe("file-name")
    expect(firstStep({ ...saving, name_conflict: true })).toBe("file-name")
    expect(firstStep(creating)).toBe("new-relation")
    expect(firstStep(adding)).toBe("into-relation")
    expect(firstStep({ ...copying, available: false, name_conflict: true })).toBe("conflict")
    expect(firstStep(copying)).toBe("run")
  })

  it("names the ticked table for rows added to it, and the place for the rest", () => {
    const intent = {
      destinationLabel: "public",
      targetLabel: "orders",
    } as CrossPasteIntent

    expect(offerPlace(adding, intent)).toBe("orders")
    expect(offerPlace(creating, intent)).toBe("public")
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
