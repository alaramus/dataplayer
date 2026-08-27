import { describe, expect, it } from "vitest"

import { moveSort, toggleMultiSort, toggleSingleSort } from "./sortModel"

describe("ordered sorting", () => {
  it("cycles a single column through asc, desc and none", () => {
    expect(toggleSingleSort([], "name")).toEqual([{ column: "name", descending: false }])
    expect(toggleSingleSort([{ column: "name", descending: false }], "name")).toEqual([
      { column: "name", descending: true },
    ])
    expect(toggleSingleSort([{ column: "name", descending: true }], "name")).toEqual([])
  })

  it("normal sorting replaces another column", () => {
    expect(toggleSingleSort([{ column: "id", descending: false }], "name")).toEqual([
      { column: "name", descending: false },
    ])
  })

  it("shift sorting keeps earlier priority", () => {
    expect(toggleMultiSort([{ column: "name", descending: false }], "created_at")).toEqual([
      { column: "name", descending: false },
      { column: "created_at", descending: false },
    ])
  })

  it("shift sorting cycles one column without moving it", () => {
    const sort = [
      { column: "name", descending: false },
      { column: "created_at", descending: false },
    ]

    expect(toggleMultiSort(sort, "name")).toEqual([
      { column: "name", descending: true },
      { column: "created_at", descending: false },
    ])
  })

  it("moves one key while preserving directions", () => {
    const sort = [
      { column: "name", descending: true },
      { column: "created_at", descending: false },
    ]

    expect(moveSort(sort, 1, -1)).toEqual([sort[1], sort[0]])
  })
})
