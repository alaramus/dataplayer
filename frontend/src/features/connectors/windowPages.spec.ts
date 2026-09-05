import { describe, expect, it } from "vitest"

import { OPTIONS_PAGE, PERMISSIONS_PAGE, windowPages } from "./windowPages"

describe("the pages of a connection window", () => {
  it("puts what this application asks after how to reach the connection", () => {
    // Both pages are there while a connection is being created as well:
    // whoever registers a source is the person who knows whether anybody
    // should be able to write through it, and asking afterwards left it open
    // until somebody went back (D66).
    const pages = windowPages([{ id: "general" }])

    expect(pages.map((page) => page.id)).toEqual([
      "general",
      OPTIONS_PAGE,
      PERMISSIONS_PAGE,
    ])
    expect(pages.slice(1)).toEqual([
      { id: OPTIONS_PAGE, label: "Options", owner: "options" },
      { id: PERMISSIONS_PAGE, label: "Permissions", owner: "permissions" },
    ])
  })

  it("names the group a field falls into when its model says nothing", () => {
    // "general" is this application's own fallback and says nothing about what
    // the page holds; a group the source named is shown under that name, in
    // the order it declared them.
    expect(windowPages([{ id: "general" }, { id: "tunnel" }]).map((page) => page.label))
      .toEqual(["Connection", "tunnel", "Options", "Permissions"])
  })

  it("keeps its own pages distinct from a source's groups of the same names", () => {
    // Two pages answering to one id would be one page with two contents.
    const pages = windowPages([
      { id: "general" },
      { id: OPTIONS_PAGE },
      { id: PERMISSIONS_PAGE },
    ])

    expect(new Set(pages.map((page) => page.id)).size).toBe(pages.length)
    expect(pages.filter((page) => page.owner === "options")).toHaveLength(1)
    expect(pages.filter((page) => page.owner === "permissions")).toHaveLength(1)
  })
})
