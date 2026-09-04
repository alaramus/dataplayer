import { describe, expect, it } from "vitest"

import { PERMISSIONS_PAGE, windowPages } from "./windowPages"

describe("the pages of a connection window", () => {
  it("puts what may be done through the connection after how to reach it", () => {
    // The page is there while a connection is being created as well: whoever
    // registers a source is the person who knows whether anybody should be
    // able to write through it, and asking afterwards left it open until
    // somebody went back (D66).
    const pages = windowPages([{ id: "general" }])

    expect(pages.map((page) => page.id)).toEqual(["general", PERMISSIONS_PAGE])
    expect(pages.at(-1)).toEqual({
      id: PERMISSIONS_PAGE,
      label: "Permissions",
      permissions: true,
    })
  })

  it("names the group a field falls into when its model says nothing", () => {
    // "general" is this application's own fallback and says nothing about what
    // the page holds; a group the source named is shown under that name, in
    // the order it declared them.
    expect(windowPages([{ id: "general" }, { id: "tunnel" }]).map((page) => page.label))
      .toEqual(["Connection", "tunnel", "Permissions"])
  })

  it("keeps its own page distinct from a source's group of the same name", () => {
    // Two pages answering to one id would be one page with two contents.
    const pages = windowPages([{ id: "general" }, { id: PERMISSIONS_PAGE }])

    expect(new Set(pages.map((page) => page.id)).size).toBe(pages.length)
    expect(pages.filter((page) => page.permissions)).toHaveLength(1)
  })
})
