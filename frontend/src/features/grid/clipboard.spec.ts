import { describe, expect, it } from "vitest"

import { fromTsv, toTsv } from "./clipboard"

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

  it("tells an empty string apart from nothing at all", () => {
    expect(toTsv([["", null]])).toBe('""\t')
  })
})

describe("TSV clipboard text, read back", () => {
  it("survives its own round trip, empty string and null included", () => {
    const matrix = [
      ["a\tb", "line\nnext"],
      ["", null],
      ['say "yes"', "plain"],
    ]

    expect(fromTsv(toTsv(matrix))).toEqual(matrix)
  })

  it("reads what a spreadsheet writes, trailing newline and all", () => {
    expect(fromTsv("a\tb\r\nc\td\r\n")).toEqual([
      ["a", "b"],
      ["c", "d"],
    ])
  })

  it("refuses text that is not a rectangle", () => {
    expect(fromTsv("a\tb\r\nc")).toBeNull()
    expect(fromTsv("")).toBeNull()
  })
})
