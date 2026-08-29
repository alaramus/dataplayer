import { describe, expect, it } from "vitest"

import type { FetchColumn } from "@/client"

import type { Filter, GridQueryState } from "./types"
import {
  buildFetchRequest,
  prunedToColumns,
  withFilters,
  withPage,
  withPageSize,
  withSort,
} from "./queryState"

const FILTER: Filter = { column: "status", op: "eq", value: "active" }

const STATE: GridQueryState = {
  page: 4,
  pageSize: 100,
  filters: [],
  sort: [],
}

describe("grid query transitions", () => {
  it("resets the page when filters change", () => {
    const next = withFilters(STATE, [FILTER])

    expect(next.page).toBe(0)
    expect(next.filters).toEqual([FILTER])
  })

  it("resets the page when ordered sort changes", () => {
    const sort = [
      { column: "status", descending: false },
      { column: "name", descending: true },
    ]

    expect(withSort(STATE, sort)).toEqual({ ...STATE, page: 0, sort })
  })

  it("resets the page when page size changes", () => {
    expect(withPageSize(STATE, 250)).toEqual({ ...STATE, page: 0, pageSize: 250 })
  })

  it("turning a page changes only the page", () => {
    expect(withPage(STATE, 3)).toEqual({ ...STATE, page: 3 })
  })

  it("builds the bounded request without mutating query state", () => {
    const state: GridQueryState = {
      page: 2,
      pageSize: 50,
      filters: [FILTER],
      sort: [{ column: "name", descending: true }],
    }
    const snapshot = structuredClone(state)

    expect(buildFetchRequest("public.projects", state)).toEqual({
      node_id: "public.projects",
      limit: 50,
      offset: 100,
      filters: [FILTER],
      sort: [{ column: "name", descending: true }],
    })
    expect(state).toEqual(snapshot)
  })
})

describe("a query the relation can no longer answer", () => {
  const column = (name: string): FetchColumn => ({
    name,
    type: { sql: "text", category: "string" },
  })

  it("keeps what still exists and names what went", () => {
    const state: GridQueryState = {
      page: 3,
      pageSize: 100,
      filters: [FILTER, { column: "owner", op: "eq", value: "ann" }],
      sort: [
        { column: "owner", descending: true },
        { column: "name", descending: false },
      ],
    }

    const { state: pruned, dropped } = prunedToColumns(state, [
      column("status"),
      column("name"),
    ])

    // Named once, though "owner" was both filtered and sorted on.
    expect(dropped).toEqual(["owner"])
    expect(pruned.filters).toEqual([FILTER])
    expect(pruned.sort).toEqual([{ column: "name", descending: false }])
    // The surviving query describes fewer rows, so the page it was on may not
    // exist any more.
    expect(pruned.page).toBe(0)
  })

  it("leaves a query every column of which still exists exactly as it was", () => {
    const state: GridQueryState = {
      page: 3,
      pageSize: 100,
      filters: [FILTER],
      sort: [{ column: "name", descending: true }],
    }

    const { state: pruned, dropped } = prunedToColumns(state, [
      column("status"),
      column("name"),
    ])

    expect(dropped).toEqual([])
    expect(pruned).toBe(state)
  })
})
