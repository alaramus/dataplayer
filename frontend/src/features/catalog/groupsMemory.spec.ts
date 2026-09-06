import { beforeEach, describe, expect, it } from "vitest"

import { rememberGroups, rememberedGroups } from "./groupsMemory"

beforeEach(() => {
  localStorage.clear()
})

describe("what the catalog remembers about a connection's groupings", () => {
  it("says nothing at all before anybody has chosen", () => {
    // Not an empty list: nothing chosen and everything turned off are two
    // different answers, and only the second is the user's.
    expect(rememberedGroups("c1")).toBeUndefined()
  })

  it("gives back exactly what was chosen, including nothing", () => {
    rememberGroups("c1", ["public"])
    expect(rememberedGroups("c1")).toEqual(["public"])

    rememberGroups("c1", [])
    expect(rememberedGroups("c1")).toEqual([])
  })

  it("keeps one connection's choice out of another's", () => {
    rememberGroups("c1", ["public"])

    expect(rememberedGroups("c2")).toBeUndefined()
  })

  it("ignores what it cannot read", () => {
    rememberGroups("c1", ["public"])
    const key = Object.keys(localStorage).find((one) => one.includes("catalog-groups"))
    localStorage.setItem(key ?? "", "{ not json")

    expect(rememberedGroups("c1")).toBeUndefined()
  })
})
