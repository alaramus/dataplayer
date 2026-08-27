import { beforeEach, describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import type { StoredGridState } from "./types"
import {
  loadGridState,
  loadPageSize,
  parseGridState,
  reconcileGridState,
  saveGridState,
  savePageSize,
} from "./persist"

const ID_COLUMN: FetchColumn = {
  name: "id",
  type: { sql: "bigint", category: "number" },
  sortable: true,
  filter_operators: ["eq", "in", "is_null"],
}
const NAME_COLUMN: FetchColumn = {
  name: "name",
  type: { sql: "text", category: "string" },
  sortable: true,
  filter_operators: ["eq", "contains", "is_null"],
}
const CREATED_COLUMN: FetchColumn = {
  name: "created_at",
  type: { sql: "timestamp with time zone", category: "datetime" },
  sortable: true,
  filter_operators: ["eq", "gt", "is_null"],
}

const STORED: StoredGridState = {
  columnOrder: ["name", "id"],
  columnVisibility: { id: false, name: true },
  columnSizing: { id: 120, name: 240 },
  pinnedLeft: ["name"],
  filters: [{ column: "name", op: "contains", value: "core" }],
  sort: [{ column: "name", descending: false }],
}

const envelope = (state: StoredGridState = STORED) => JSON.stringify({ version: 1, state })

describe("stored grid state", () => {
  beforeEach(() => localStorage.clear())

  it("refuses invalid JSON", () => {
    expect(parseGridState("{ not json")).toBeNull()
  })

  it("refuses an unknown version", () => {
    expect(parseGridState(JSON.stringify({ version: 2, state: STORED }))).toBeNull()
  })

  it("refuses unknown fields instead of silently accepting another layout model", () => {
    const state = { ...STORED, pinnedRight: ["id"] }

    expect(parseGridState(JSON.stringify({ version: 1, state }))).toBeNull()
  })

  it("round trips relation state independently by connector and node", () => {
    saveGridState("connector-a", "public.projects", STORED)

    expect(loadGridState("connector-a", "public.projects")).toEqual(STORED)
    expect(loadGridState("connector-b", "public.projects")).toBeNull()
    expect(loadGridState("connector-a", "public.people")).toBeNull()
  })

  it("uses one page size for every grid", () => {
    expect(loadPageSize()).toBe(100)

    savePageSize(250)

    expect(loadPageSize()).toBe(250)
  })

  it("keeps valid state and appends a newly discovered column", () => {
    const reconciled = reconcileGridState(STORED, [ID_COLUMN, NAME_COLUMN, CREATED_COLUMN])

    expect(reconciled.columnOrder).toEqual(["name", "id", "created_at"])
    expect(reconciled.filters).toEqual(STORED.filters)
    expect(reconciled.sort).toEqual(STORED.sort)
  })

  it("drops missing columns from every part of the layout", () => {
    const stored: StoredGridState = {
      ...STORED,
      columnOrder: ["gone", "name", "id"],
      columnVisibility: { gone: false, id: false },
      columnSizing: { gone: 300, name: 240 },
      pinnedLeft: ["gone", "name"],
    }

    expect(reconcileGridState(stored, [ID_COLUMN, NAME_COLUMN])).toMatchObject({
      columnOrder: ["name", "id"],
      columnVisibility: { id: false },
      columnSizing: { name: 240 },
      pinnedLeft: ["name"],
    })
  })

  it("drops operations the current column contract no longer allows", () => {
    const stored: StoredGridState = {
      ...STORED,
      filters: [{ column: "id", op: "eq", value: "1" }],
      sort: [{ column: "id", descending: false }],
    }
    const unfilterableId: FetchColumn = {
      ...ID_COLUMN,
      sortable: false,
      filter_operators: [],
    }

    const reconciled = reconcileGridState(stored, [unfilterableId])

    expect(reconciled.sort).toEqual([])
    expect(reconciled.filters).toEqual([])
  })

  it("drops a filter when its particular operator disappeared", () => {
    const nameWithoutContains: FetchColumn = {
      ...NAME_COLUMN,
      filter_operators: ["eq", "is_null"],
    }

    expect(reconcileGridState(STORED, [ID_COLUMN, nameWithoutContains]).filters).toEqual([])
  })

  it("accepts the exact versioned envelope", () => {
    expect(parseGridState(envelope())).toEqual(STORED)
  })
})
