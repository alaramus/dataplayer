import { describe, expect, it } from "vitest"

import { filenameStem, parseDelimited } from "./delimitedFile"

describe("the delimited-file chooser", () => {
  it("reads quoted separators and line breaks without adding a trailing row", () => {
    const parsed = parseDelimited(
      'id,note\n1,"hello, world"\n2,"two\nlines"\n',
      "notes.csv"
    )

    expect(parsed).toEqual({
      columns: ["id", "note"],
      preview: [
        ["1", "hello, world"],
        ["2", "two\nlines"],
      ],
    })
  })

  it("normalizes empty and duplicate headers the same way as the server", () => {
    expect(parseDelimited("id,,id\n1,2,3", "values.csv").columns).toEqual([
      "id",
      "column_2",
      "id_3",
    ])
  })

  it("uses the uploaded filename as the initial table name", () => {
    expect(filenameStem("regions.2026.csv")).toBe("regions.2026")
  })
})
