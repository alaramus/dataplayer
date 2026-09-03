import { describe, expect, it } from "vitest"

import type { NodeSearchResult } from "@/client"
import { at, first } from "@/shared/testing/collections"

import { foundNodes, searchSummary } from "./search"

const match = (id: string, name: string, location: string) => ({
  node: {
    id,
    name,
    kind: "file" as const,
    has_children: false,
    size_bytes: 12,
    representations: [{ kind: "text" as const, title: "View as text" }],
    summarizable: true,
  },
  parent_id: location === "" ? null : location,
  location,
})

const result = (over: Partial<NodeSearchResult> = {}): NodeSearchResult => ({
  matches: [match("notes.txt", "notes.txt", ""), match("a/b/notes.md", "notes.md", "a/b")],
  complete: true,
  notice: null,
  ...over,
})

describe("what a search leaves on the screen", () => {
  it("draws a match as the row its level would have drawn", () => {
    const found = foundNodes("notes", result())

    const row = first(found.rows)
    expect(row.label).toBe("notes.txt")
    // Icon, role and caption all come from the shared mapping, so a found row
    // opens and reads exactly like a listed one.
    expect(row.role).toBe("leaf")
    expect(row.readable).toBe(true)
    expect(row.caption).toBe("12 B")
  })

  it("carries where each one was found, and nothing where that is the top", () => {
    const found = foundNodes("notes", result())

    expect(first(found.rows).location).toBeUndefined()
    expect(at(found.rows, 1).location).toBe("a/b")
  })

  it("says how many matched when that is all of them", () => {
    expect(searchSummary(foundNodes("notes", result()))).toBe('2 matches for “notes”')
  })

  it("says it stopped looking when it did, because that means type more", () => {
    const stopped = foundNodes("notes", result({ complete: false }))

    expect(searchSummary(stopped)).toBe('First 2 matches for “notes”')
    expect(stopped.complete).toBe(false)
  })

  it("says nothing matched rather than showing an empty count", () => {
    const empty = foundNodes("zzz", result({ matches: [] }))

    expect(searchSummary(empty)).toBe('Nothing matches “zzz”')
    expect(empty.rows).toEqual([])
  })

  it("keeps the reason a search stopped, in the source's words", () => {
    const stopped = foundNodes(
      "notes",
      result({ complete: false, notice: "The first 100 matches; there may be more" })
    )

    expect(stopped.notice).toBe("The first 100 matches; there may be more")
  })

  it("shows the line a match was found on instead of the file's size", () => {
    const inside = foundNodes(
      "timeout",
      result({
        matches: [
          {
            ...match("server.log", "server.log", ""),
            excerpt: "2026-08-31 10:02:11 ERROR upstream timeout after 30s",
          },
        ],
      })
    )

    expect(first(inside.rows).caption).toBe(
      "2026-08-31 10:02:11 ERROR upstream timeout after 30s"
    )
  })

  it("counts one match as one", () => {
    const one = foundNodes("notes", result({ matches: [match("x.txt", "x.txt", "")] }))

    expect(searchSummary(one)).toBe('1 match for “notes”')
  })
})
