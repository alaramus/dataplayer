import { describe, expect, it } from "vitest"

import { filterPairs, momentAgo, otherRepresentations, valueText } from "./view"

describe("a view's values as text (D420)", () => {
  it("says an empty value as a dash, not as nothing", () => {
    expect(valueText({ kind: "empty" })).toBe("—")
  })

  it("says a size in the reader's units", () => {
    expect(valueText({ kind: "bytes", value: 1024 })).toBe("1.0 KB")
  })

  it("says how long ago, and how far ahead", () => {
    const now = Date.parse("2026-11-21T12:00:00Z")
    expect(momentAgo("2026-11-21T11:00:00Z", now)).toBe("1h ago")
    expect(momentAgo("2026-11-21T12:05:00Z", now)).toBe("in 5m")
  })
})

describe("filtering pairs (D421)", () => {
  const pairs = [
    { name: "DB_PASSWORD", value: "hunter2", sensitive: true },
    { name: "LOG_LEVEL", value: "debug" },
  ]

  it("matches a name or a value, case folded", () => {
    expect(filterPairs(pairs, "log").map((one) => one.name)).toEqual(["LOG_LEVEL"])
    expect(filterPairs(pairs, "DEBUG").map((one) => one.name)).toEqual(["LOG_LEVEL"])
  })

  it("never matches a hidden value, which would say what it is", () => {
    expect(filterPairs(pairs, "hunter")).toEqual([])
    expect(filterPairs(pairs, "password").map((one) => one.name)).toEqual(["DB_PASSWORD"])
  })
})

describe("the other ways a node opens (D419)", () => {
  it("are every declared representation but the one shown", () => {
    const declared = [
      { kind: "view" as const, title: "Overview" },
      { kind: "tree" as const, title: "As JSON" },
    ]
    expect(otherRepresentations(declared, "view")).toEqual([{ kind: "tree", title: "As JSON" }])
    expect(otherRepresentations(undefined, "view")).toEqual([])
  })
})
