import { beforeEach, describe, expect, it } from "vitest"

import type { QueryDocumentPublic } from "@/client"

import {
  changed,
  clearShadow,
  copyTitle,
  draftOf,
  keepMine,
  readShadow,
  recoverable,
  saveFor,
  writeShadow,
} from "./draft"

const DOCUMENT: QueryDocumentPublic = {
  id: "d1",
  connector_id: "c1",
  connector_label: "local pg",
  title: null,
  body: "select 1",
  revision: 3,
  search_path: ["public"],
  layout: { split_ratio: 0.6, wrap: false },
}

describe("what an autosave carries", () => {
  it("sends nothing when nothing differs", () => {
    expect(saveFor(DOCUMENT, draftOf(DOCUMENT))).toBeNull()
    expect(changed(DOCUMENT, draftOf(DOCUMENT))).toBe(false)
  })

  it("sends only what changed, on the revision it started from", () => {
    const save = saveFor(DOCUMENT, { ...draftOf(DOCUMENT), body: "select 2" })

    expect(save).toEqual({ revision: 3, body: "select 2" })
  })

  it("sends a title taken off as null rather than leaving it out", () => {
    const named = { ...DOCUMENT, title: "Daily counts" }

    expect(saveFor(named, { ...draftOf(named), title: null })).toEqual({
      revision: 3,
      title: null,
    })
  })

  it("keeps the rest of the layout when only wrapping changes", () => {
    const save = saveFor(DOCUMENT, { ...draftOf(DOCUMENT), wrap: true })

    expect(save).toEqual({ revision: 3, layout: { split_ratio: 0.6, wrap: true } })
  })

  it("sends where the line between the two halves was left", () => {
    const save = saveFor(DOCUMENT, { ...draftOf(DOCUMENT), split: 0.35 })

    expect(save).toEqual({ revision: 3, layout: { split_ratio: 0.35, wrap: false } })
  })

  it("reads a layout the server left to its default", () => {
    const bare: QueryDocumentPublic = { ...DOCUMENT, layout: {} }

    expect(draftOf(bare).wrap).toBe(false)
    expect(draftOf(bare).split).toBe(0.6)
    expect(changed(bare, draftOf(bare))).toBe(false)
  })
})

describe("resolving a conflict", () => {
  it("keeps your own text on top of the revision that is there now", () => {
    const remote: QueryDocumentPublic = { ...DOCUMENT, revision: 9, body: "select 9" }

    expect(
      keepMine(remote, { body: "mine", title: "Mine", wrap: true, split: 0.4 })
    ).toEqual({
      revision: 9,
      body: "mine",
      title: "Mine",
      layout: { split_ratio: 0.4, wrap: true },
    })
  })

  it("names a copy after what it came from, and says so for a draft", () => {
    expect(copyTitle("Daily counts")).toBe("Daily counts (copy)")
    expect(copyTitle(null)).toBe("Unsaved copy")
  })
})

describe("the unsynchronised shadow of one tab", () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it("comes back exactly as it was written", () => {
    writeShadow({ documentId: "d1", revision: 3, body: "select 2", title: "Mine" })

    expect(readShadow("d1")).toEqual({
      documentId: "d1",
      revision: 3,
      body: "select 2",
      title: "Mine",
    })
  })

  it("is offered only when it holds text the server has not got", () => {
    const mine = { documentId: "d1", revision: 3, body: "select 2", title: null }

    expect(recoverable(mine, DOCUMENT)).toBe(true)
    expect(recoverable({ ...mine, body: DOCUMENT.body }, DOCUMENT)).toBe(false)
    expect(recoverable(null, DOCUMENT)).toBe(false)
  })

  it("is not offered once the document has moved on without it", () => {
    // Written against revision 3, but the server is at 4: what is here is
    // older than what is there, and calling it "your unsaved work" would lie
    // about which of the two is newer.
    const stale = { documentId: "d1", revision: 3, body: "select 2", title: null }

    expect(recoverable(stale, { ...DOCUMENT, revision: 4 })).toBe(false)
  })

  it("goes when it is cleared, and reads as nothing when it was never there", () => {
    writeShadow({ documentId: "d1", revision: 3, body: "select 2", title: null })
    clearShadow("d1")

    expect(readShadow("d1")).toBeNull()
    expect(readShadow("never-written")).toBeNull()
  })

  it("answers nothing rather than throwing when the storage holds rubbish", () => {
    sessionStorage.setItem("dp.query.shadow.d1", "{not json")

    expect(readShadow("d1")).toBeNull()
  })

  it("keeps one document's text out of another's", () => {
    writeShadow({ documentId: "d1", revision: 3, body: "mine", title: null })

    expect(readShadow("d2")).toBeNull()
  })
})
