import { describe, expect, it } from "vitest"

import { columnTally, filenameStem, parseDelimited, readDelimited } from "./delimitedFile"

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

describe("what the block of columns says about itself", () => {
  it("counts what would be created", () => {
    expect(columnTally(5, 5, 0)).toBe("all 5")
    expect(columnTally(5, 2, 0)).toBe("2 of 5")
    expect(columnTally(5, 0, 0)).toBe("none of 5")
  })

  it("says why nothing can be created instead of counting", () => {
    // A compact field has no room under it for a message, and the button it
    // refuses is at the other end of the dialog.
    expect(columnTally(5, 5, 1)).toBe("1 of them needs a name")
    expect(columnTally(5, 5, 2)).toBe("2 of them need a name")
  })
})

describe("a file larger than one request takes", () => {
  it("is previewed from its beginning, its size left to the server", async () => {
    const row = "1,Customer,Moscow\n"
    const file = new File(["id,name,city\n", row.repeat(1_000_000)], "big.csv")

    const read = await readDelimited(file)

    expect(file.size).toBeGreaterThan(16 * 1024 * 1024)
    expect(read.columns).toEqual(["id", "name", "city"])
    expect(read.preview[0]).toEqual(["1", "Customer", "Moscow"])
  })
})

