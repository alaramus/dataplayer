import { describe, expect, it } from "vitest"

import type { HypertableDesignState } from "@/client"

import { completed, draftFrom } from "./draft"

const state: HypertableDesignState = {
  node_id: "lab.events",
  design: {
    chunk_interval: { amount: 1, unit: "week" },
    hash_dimensions: [{ column: "device", partitions: 4 }],
    columnstore: {
      enabled: true,
      segment_by: { mode: "columns", columns: ["device"] },
      order_by: {
        mode: "columns",
        columns: [{ column: "observed_at", descending: true, nulls_first: true }],
      },
      merge_interval: { amount: 2, unit: "week" },
    },
    retention: { kind: "current" },
    columnstore_policy: { kind: "older_than", older_than: { amount: 3, unit: "month" } },
    reorder_index: "events_device",
    tablespaces: ["pg_default"],
  },
  interval_units: ["minute", "hour", "day", "week"],
  policy_units: ["hour", "day", "week", "month", "year"],
}

describe("hypertable settings draft", () => {
  it("returns the design it was read from, unchanged", () => {
    const draft = draftFrom(state)
    expect(draft).not.toBeNull()
    expect(completed(draft!)).toEqual({ design: state.design })
  })

  it("has no draft for a table the server will not design", () => {
    expect(draftFrom({ node_id: "lab.plain", reason: "Choose an owned hypertable" })).toBeNull()
  })

  it("keeps a policy it cannot represent as it is", () => {
    const draft = draftFrom(state)!
    expect(draft.retention.mode).toBe("current")
    draft.retention.mode = "none"
    const answer = completed(draft)
    expect("design" in answer && answer.design.retention).toBeNull()
  })

  it("says what an incomplete form lacks rather than sending it", () => {
    const draft = draftFrom(state)!
    draft.segmentMode = "columns"
    draft.segmentColumns = []
    expect(completed(draft)).toEqual({ missing: "Choose the columns to segment by" })

    const empty = draftFrom(state)!
    empty.retention = { mode: "older_than", duration: { amount: null, unit: "month" } }
    expect(completed(empty)).toEqual({ missing: "Enter the retention age" })
  })

  it("drops every columnstore setting when the columnstore is off", () => {
    const draft = draftFrom(state)!
    draft.columnstore = false
    draft.columnstorePolicy.mode = "none"
    const answer = completed(draft)
    expect("design" in answer && answer.design.columnstore).toEqual({ enabled: false })
  })

  it("leaves out an order row whose column was not chosen", () => {
    const draft = draftFrom(state)!
    draft.orderColumns.push({ column: "", descending: false, nullsFirst: false })
    const answer = completed(draft)
    expect("design" in answer && answer.design.columnstore?.order_by).toEqual(
      state.design?.columnstore?.order_by
    )
  })
})
