import { describe, expect, it } from "vitest"

import {
  droppedByReconciliation,
  linkFor,
  pageSizeOf,
  storedFromView,
  viewOfGrid,
} from "./sharedView"
import type { RowsView } from "@/client"
import { reconcileGridState } from "@/features/grid/persist"
import type { FetchColumn } from "@/features/grid/types"

const layout = {
  columnOrder: ["name", "size"],
  columnVisibility: { size: false },
  columnSizing: { name: 240 },
  pinnedLeft: ["name"],
}

const query = {
  page: 3,
  pageSize: 250 as const,
  filters: [{ column: "name", op: "contains" as const, value: "report" }],
  sort: [{ column: "name", descending: true }],
}

function column(name: string): FetchColumn {
  return {
    name,
    type: { sql: "text", category: "string" },
    sortable: true,
    filter_operators: ["contains", "eq"],
  }
}

describe("what a link carries", () => {
  it("takes the query and the arrangement, and leaves the page behind", () => {
    // D59: under a filter the reader's page three is not the sender's, so an
    // offset would point somewhere else while the query means the same thing.
    const view = viewOfGrid(query, layout)

    expect(view).toEqual({
      kind: "rows",
      filters: query.filters,
      sort: query.sort,
      page_size: 250,
      column_order: ["name", "size"],
      pinned_left: ["name"],
      column_visibility: { size: false },
      column_sizing: { name: 240 },
    })
    expect(view).not.toHaveProperty("page")
  })

  it("comes back as the shape a restored tab uses", () => {
    expect(storedFromView(viewOfGrid(query, layout))).toEqual({
      columnOrder: ["name", "size"],
      columnVisibility: { size: false },
      columnSizing: { name: 240 },
      pinnedLeft: ["name"],
      filters: query.filters,
      sort: query.sort,
    })
  })

  it("survives a body with nothing in it", () => {
    expect(storedFromView({ kind: "rows" })).toEqual({
      columnOrder: [],
      columnVisibility: {},
      columnSizing: {},
      pinnedLeft: [],
      filters: [],
      sort: [],
    })
  })
})

describe("the page size of a shared view", () => {
  it("is taken when the grid offers it", () => {
    expect(pageSizeOf({ kind: "rows", page_size: 500 })).toBe(500)
  })

  it("falls back when it is a size this grid does not offer", () => {
    // A body is validated by the server against a ceiling, not against the
    // four sizes this grid shows, so 77 is a shape the client must survive.
    expect(pageSizeOf({ kind: "rows", page_size: 77 })).toBe(100)
    expect(pageSizeOf({ kind: "rows" }, 250)).toBe(250)
  })
})

describe("what the relation no longer has", () => {
  it("is named after reconciliation drops it", () => {
    const view: RowsView = {
      kind: "rows",
      filters: [
        { column: "name", op: "contains", value: "a" },
        { column: "gone", op: "contains", value: "b" },
      ],
      sort: [{ column: "also_gone", descending: false }],
    }
    const wanted = storedFromView(view)
    const kept = reconcileGridState(wanted, [column("name")])

    expect(droppedByReconciliation(wanted, kept)).toEqual(["gone", "also_gone"])
  })

  it("is nothing when the relation still has every column", () => {
    const wanted = storedFromView(viewOfGrid(query, layout))
    const kept = reconcileGridState(wanted, [column("name"), column("size")])

    expect(droppedByReconciliation(wanted, kept)).toEqual([])
  })
})

describe("the address itself", () => {
  it("is the token under /s of wherever the reader is", () => {
    expect(linkFor("AbC123", "https://data.example.com")).toBe(
      "https://data.example.com/s/AbC123"
    )
  })
})
