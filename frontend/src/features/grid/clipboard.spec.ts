import { describe, expect, it, vi } from "vitest"

import { toTsv, writeSelection } from "./clipboard"

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

  it("has one browser boundary for writing selection text", async () => {
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue()

    await writeSelection("a\tb")

    expect(writeText).toHaveBeenCalledWith("a\tb")
  })
})
