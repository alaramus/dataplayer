import type { HypertableDesign, HypertableDesignState } from "@/client"

/**
 * The hypertable settings form, and the one place it becomes a design (D207).
 *
 * The form holds what a person is typing — an empty amount, a list mode with
 * no columns yet — which the design model cannot. Whether the design is
 * allowed is the server's question; this only says whether it is complete.
 */

export type DurationUnit = "second" | "minute" | "hour" | "day" | "week" | "month" | "year"
export type PolicyMode = "none" | "older_than" | "current"

export interface DurationDraft {
  amount: number | null
  unit: DurationUnit
}

export interface PolicyDraft {
  mode: PolicyMode
  duration: DurationDraft
}

export interface OrderDraft {
  column: string
  descending: boolean
  nullsFirst: boolean
}

export interface HashDraft {
  column: string
  partitions: number | null
  /** Already on the hypertable: its count may change, it may not go. */
  existing: boolean
}

export interface Draft {
  chunkInterval: DurationDraft
  hash: HashDraft[]
  columnstore: boolean
  segmentMode: "default" | "none" | "columns"
  segmentColumns: string[]
  orderMode: "default" | "columns"
  orderColumns: OrderDraft[]
  merge: boolean
  mergeInterval: DurationDraft
  retention: PolicyDraft
  columnstorePolicy: PolicyDraft
  /** "" for no reorder policy. */
  reorderIndex: string
  tablespaces: string[]
}

export type Completed = { design: HypertableDesign } | { missing: string }

type Duration = { amount: number; unit: DurationUnit }
type Policy = HypertableDesign["retention"]

function durationDraft(value: Duration | null | undefined, fallback: DurationDraft): DurationDraft {
  return value ? { amount: value.amount, unit: value.unit } : { ...fallback }
}

function policyDraft(value: Policy, fallback: DurationDraft): PolicyDraft {
  if (value === null || value === undefined) return { mode: "none", duration: { ...fallback } }
  if (value.kind === "current") return { mode: "current", duration: { ...fallback } }
  return { mode: "older_than", duration: durationDraft(value.older_than, fallback) }
}

export function draftFrom(state: HypertableDesignState): Draft | null {
  const design = state.design
  if (!design) return null
  const store = design.columnstore ?? { enabled: false }
  const segment = store.segment_by ?? { mode: "none" }
  const order = store.order_by ?? { mode: "default" }
  const policyUnit: DurationUnit = state.policy_units?.includes("month") ? "month" : "week"
  const intervalUnit: DurationUnit = state.interval_units?.includes("day") ? "day" : "week"
  return {
    chunkInterval: durationDraft(design.chunk_interval, { amount: null, unit: intervalUnit }),
    hash: (design.hash_dimensions ?? []).map((item) => ({
      column: item.column,
      partitions: item.partitions,
      existing: true,
    })),
    columnstore: store.enabled,
    segmentMode: segment.mode,
    segmentColumns: segment.mode === "columns" ? [...segment.columns] : [],
    orderMode: order.mode,
    orderColumns:
      order.mode === "columns"
        ? order.columns.map((key) => ({
            column: key.column,
            descending: key.descending,
            nullsFirst: key.nulls_first,
          }))
        : [],
    merge: store.merge_interval !== null && store.merge_interval !== undefined,
    mergeInterval: durationDraft(store.merge_interval, { amount: null, unit: intervalUnit }),
    retention: policyDraft(design.retention, { amount: null, unit: policyUnit }),
    columnstorePolicy: policyDraft(design.columnstore_policy, { amount: null, unit: policyUnit }),
    reorderIndex: design.reorder_index ?? "",
    tablespaces: [...(design.tablespaces ?? [])],
  }
}

function whole(value: number | null): value is number {
  return value !== null && Number.isInteger(value) && value > 0
}

function duration(value: DurationDraft): Duration | null {
  return whole(value.amount) ? { amount: value.amount, unit: value.unit } : null
}

function policy(value: PolicyDraft): Policy | "missing" {
  if (value.mode === "none") return null
  if (value.mode === "current") return { kind: "current" }
  const older = duration(value.duration)
  return older === null ? "missing" : { kind: "older_than", older_than: older }
}

/** The design the form describes, or what it still lacks. */
export function completed(draft: Draft): Completed {
  const chunk = duration(draft.chunkInterval)
  if (chunk === null) return { missing: "Enter the chunk interval" }
  if (draft.hash.some((item) => item.column === "" || !whole(item.partitions))) {
    return { missing: "Choose a column and a number of partitions for every hash dimension" }
  }
  if (draft.columnstore && draft.segmentMode === "columns" && draft.segmentColumns.length === 0) {
    return { missing: "Choose the columns to segment by" }
  }
  const orderColumns = draft.orderColumns.filter((key) => key.column !== "")
  if (draft.columnstore && draft.orderMode === "columns" && orderColumns.length === 0) {
    return { missing: "Choose the columns to order by" }
  }
  const merge = draft.columnstore && draft.merge ? duration(draft.mergeInterval) : null
  if (draft.columnstore && draft.merge && merge === null) {
    return { missing: "Enter the merge interval" }
  }
  const retention = policy(draft.retention)
  if (retention === "missing") return { missing: "Enter the retention age" }
  const columnstorePolicy = policy(draft.columnstorePolicy)
  if (columnstorePolicy === "missing") return { missing: "Enter the columnstore policy age" }
  return {
    design: {
      chunk_interval: chunk,
      hash_dimensions: draft.hash.map((item) => ({
        column: item.column,
        partitions: item.partitions ?? 0,
      })),
      columnstore: draft.columnstore
        ? {
            enabled: true,
            segment_by:
              draft.segmentMode === "columns"
                ? { mode: "columns", columns: [...draft.segmentColumns] }
                : { mode: draft.segmentMode },
            order_by:
              draft.orderMode === "columns"
                ? {
                    mode: "columns",
                    columns: orderColumns.map((key) => ({
                      column: key.column,
                      descending: key.descending,
                      nulls_first: key.nullsFirst,
                    })),
                  }
                : { mode: "default" },
            merge_interval: merge,
          }
        : { enabled: false },
      retention,
      columnstore_policy: columnstorePolicy,
      reorder_index: draft.reorderIndex === "" ? null : draft.reorderIndex,
      tablespaces: [...draft.tablespaces],
    },
  }
}
