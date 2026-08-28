import { describe, expect, it } from "vitest"

import { toTsv } from "./clipboard"

describe("TSV clipboard text", () => {
  it("serializes a rectangle in display order without headers", () => {
    expect(
      toTsv([
        ["a", "b"],
        ["c", null],
      ])
    ).toBe("a\tb\r\nc\t")
  })

  it("quotes tabs, lines and quotes", () => {
    expect(toTsv([["a\tb", "line\nnext", 'say "yes"']])).toBe(
      '"a\tb"\t"line\nnext"\t"say ""yes"""'
    )
  })
})
