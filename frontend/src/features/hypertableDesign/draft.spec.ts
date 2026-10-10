import { describe, expect, it } from "vitest"

import type { HypertableDesignState } from "@/client"

import { completed, draftFrom, nowKey, retimed } from "./draft"

const state: HypertableDesignState = {
  node_id: "lab.events",
  design: {
    time_column: "observed_at",
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
      sparse_indexes: { mode: "columns", indexes: [{ column: "device", kind: "bloom" }] },
    },
    retention: { kind: "current" },
    columnstore_policy: { kind: "older_than", older_than: { amount: 3, unit: "month" } },
    reorder_index: "events_device",
    tablespaces: ["pg_default"],
    integer_now: null,
    compaction_policy: true,
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

  it("asks for the column an ordinary table is converted by", () => {
    const draft = draftFrom({ ...state, hypertable: false })!
    draft.timeColumn = ""
    expect(completed(draft)).toEqual({ missing: "Choose the time column" })
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

  it("sends an integer length back with the server's own digits", () => {
    const counted: HypertableDesignState = {
      node_id: "lab.ticks",
      design: {
        time_column: "tick",
        chunk_interval: { unit: "integer", amount: "9007199254740993" },
        retention: { kind: "older_than", older_than: { unit: "integer", amount: "86400" } },
        integer_now: { kind: "existing", schema_name: "lab", name: "unix_now" },
      },
    }
    const draft = draftFrom(counted)!
    expect(draft.now.existing).toBe(nowKey({ schema_name: "lab", name: "unix_now" }))
    const answer = completed(draft)
    expect("design" in answer && answer.design.chunk_interval).toEqual({ unit: "integer", amount: "9007199254740993" })
    expect("design" in answer && answer.design.integer_now).toEqual(counted.design?.integer_now)

    draft.chunkInterval.amount = 5000
    const edited = completed(draft)
    expect("design" in edited && edited.design.chunk_interval).toEqual({ unit: "integer", amount: "5000" })
  })

  it("asks for the function a template makes, by name", () => {
    const draft = draftFrom({
      node_id: "lab.ticks",
      design: { time_column: "tick", chunk_interval: { unit: "integer", amount: "1000" } },
    })!
    draft.now = { mode: "template", existing: "", template: "epoch_seconds", name: " " }
    expect(completed(draft)).toEqual({ missing: "Name the integer_now function" })
    draft.now.name = "unix_seconds"
    const answer = completed(draft)
    expect("design" in answer && answer.design.integer_now).toEqual({
      kind: "template",
      template: "epoch_seconds",
      name: "unix_seconds",
    })
  })

  it("counts lengths anew when the table is converted by a column of another kind", () => {
    const table: HypertableDesignState = {
      ...state,
      hypertable: false,
      time_columns: [
        { name: "observed_at", type: "timestamp with time zone", orderable: true },
        {
          name: "tick",
          type: "integer",
          orderable: true,
          chunk_interval: { unit: "integer", amount: "100000" },
          now_templates: ["epoch_seconds"],
        },
      ],
    }
    const draft = draftFrom(table)!
    draft.now = { mode: "template", existing: "", template: "epoch_milliseconds", name: "clock" }
    const counted = retimed(draft, table.time_columns![1]!, table)
    expect(counted.chunkInterval).toMatchObject({ amount: 100000, unit: "integer" })
    expect(counted.columnstorePolicy.duration).toEqual({ amount: null, unit: "integer" })
    expect(counted.merge).toBe(false)
    expect(counted.now.template).toBe("epoch_seconds")
    expect(completed(counted)).toEqual({ missing: "Enter the columnstore policy age" })
    counted.columnstorePolicy.duration.amount = 500
    const answer = completed(counted)
    expect("design" in answer && answer.design.columnstore?.merge_interval).toBeNull()
  })

  it("asks for the column of every sparse index, and drops the policy with the columnstore", () => {
    const draft = draftFrom(state)!
    draft.sparseIndexes = [{ column: "", kind: "minmax" }]
    expect(completed(draft)).toEqual({ missing: "Choose the columns of the sparse indexes" })
    draft.columnstore = false
    draft.columnstorePolicy.mode = "none"
    const answer = completed(draft)
    expect("design" in answer && answer.design.compaction_policy).toBe(false)
  })
})
