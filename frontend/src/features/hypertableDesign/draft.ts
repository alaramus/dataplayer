import type { HypertableColumn, HypertableDesign, HypertableDesignState, NowFunction } from "@/client"

/**
 * The hypertable settings form, and the one place it becomes a design (D207).
 *
 * The form holds what a person is typing — an empty amount, a list mode with
 * no columns yet — which the design model cannot. Whether the design is
 * allowed is the server's question; this only says whether it is complete.
 */

export type DurationUnit = "second" | "minute" | "hour" | "day" | "week" | "month" | "year"
/** A time column's lengths are durations; an integer column's are counted in its values. */
export type LengthUnit = DurationUnit | "integer"
export type PolicyMode = "none" | "older_than" | "current"
export type NowTemplate = "epoch_seconds" | "epoch_milliseconds" | "epoch_microseconds"
export type NowMode = "none" | "current" | "existing" | "template"
export type SparseKind = "minmax" | "bloom"

export interface SparseDraft {
  column: string
  kind: SparseKind
}

export interface DurationDraft {
  amount: number | null
  unit: LengthUnit
  /**
   * The server's own digits for an integer length: a bigint can go past what
   * a number holds exactly, and an unedited length must go back unchanged.
   */
  exact?: string
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

export interface NowDraft {
  mode: NowMode
  /** A key of `nowKey`, for an existing function. */
  existing: string
  template: NowTemplate
  /** The name of a function made from a template. */
  name: string
}

export interface Draft {
  /** The column an ordinary table is converted by; a hypertable's own, which cannot change. */
  timeColumn: string
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
  now: NowDraft
  /** Sparse indexes, in the three states segmenting has (D207, from 2.22). */
  sparseMode: "default" | "none" | "columns"
  sparseIndexes: SparseDraft[]
  compaction: boolean
}

export type Completed = { design: HypertableDesign } | { missing: string }

type Span = NonNullable<HypertableDesign["chunk_interval"]>
type Policy = HypertableDesign["retention"]
type Now = HypertableDesign["integer_now"]

/** One select value per function, whatever its schema and name hold. */
export function nowKey(item: { schema_name: string; name: string }): string {
  return JSON.stringify([item.schema_name, item.name])
}

function durationDraft(value: Span | null | undefined, fallback: DurationDraft): DurationDraft {
  if (!value) return { ...fallback }
  if (value.unit === "integer") return { amount: Number(value.amount), unit: "integer", exact: value.amount }
  return { amount: value.amount, unit: value.unit ?? fallback.unit }
}

function policyDraft(value: Policy, fallback: DurationDraft): PolicyDraft {
  if (value === null || value === undefined) return { mode: "none", duration: { ...fallback } }
  if (value.kind === "current") return { mode: "current", duration: { ...fallback } }
  return { mode: "older_than", duration: durationDraft(value.older_than, fallback) }
}

function nowDraft(value: Now): NowDraft {
  const blank: NowDraft = { mode: "none", existing: "", template: "epoch_seconds", name: "" }
  if (value === null || value === undefined) return blank
  if (value.kind === "current") return { ...blank, mode: "current" }
  if (value.kind === "template") return { ...blank, mode: "template", template: value.template, name: value.name }
  return { ...blank, mode: "existing", existing: nowKey(value) }
}

/** The units a policy age starts in, for a time column or an integer one. */
function policyFallback(integer: boolean, state: HypertableDesignState): DurationDraft {
  if (integer) return { amount: null, unit: "integer" }
  return { amount: null, unit: state.policy_units?.includes("month") ? "month" : "week" }
}

export function draftFrom(state: HypertableDesignState): Draft | null {
  const design = state.design
  if (!design) return null
  const store = design.columnstore ?? { enabled: false }
  const segment = store.segment_by ?? { mode: "none" }
  const order = store.order_by ?? { mode: "default" }
  const sparse = store.sparse_indexes ?? { mode: "default" }
  const integer = design.chunk_interval?.unit === "integer"
  const policy = policyFallback(integer, state)
  const intervalUnit: DurationUnit = state.interval_units?.includes("day") ? "day" : "week"
  return {
    timeColumn: design.time_column ?? state.time_column ?? "",
    chunkInterval: durationDraft(design.chunk_interval, { amount: null, unit: integer ? "integer" : intervalUnit }),
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
    retention: policyDraft(design.retention, policy),
    columnstorePolicy: policyDraft(design.columnstore_policy, policy),
    reorderIndex: design.reorder_index ?? "",
    tablespaces: [...(design.tablespaces ?? [])],
    now: nowDraft(design.integer_now),
    sparseMode: sparse.mode,
    sparseIndexes: sparse.mode === "columns" ? sparse.indexes.map((item) => ({ ...item })) : [],
    compaction: design.compaction_policy ?? false,
  }
}

/**
 * The draft once the table is to be converted by another column (D207).
 *
 * A time column and an integer one count their lengths differently, so the
 * interval becomes the one the server proposes for the new column, and ages
 * already typed keep their numbers only while the kind of column is the same.
 */
export function retimed(draft: Draft, column: HypertableColumn, state: HypertableDesignState): Draft {
  const integer = column.chunk_interval?.unit === "integer"
  const wasInteger = draft.chunkInterval.unit === "integer"
  const fallback = policyFallback(integer, state)
  const age = (value: PolicyDraft): PolicyDraft =>
    integer === wasInteger ? value : { ...value, duration: { ...fallback } }
  const templates = column.now_templates ?? []
  return {
    ...draft,
    timeColumn: column.name,
    chunkInterval: durationDraft(column.chunk_interval, draft.chunkInterval),
    merge: integer ? false : draft.merge,
    retention: age(draft.retention),
    columnstorePolicy: age(draft.columnstorePolicy),
    now: integer
      ? {
          ...draft.now,
          template: templates.includes(draft.now.template) ? draft.now.template : (templates[0] ?? "epoch_seconds"),
          mode: draft.now.mode === "template" && templates.length === 0 ? "none" : draft.now.mode,
        }
      : { ...draft.now, mode: "none" },
  }
}

/** The functions an integer column of this type may take as integer_now. */
export function clocksFor(functions: readonly NowFunction[] | undefined, type: string | null | undefined) {
  return (functions ?? []).filter((item) => item.type === type)
}

function whole(value: number | null): value is number {
  return value !== null && Number.isSafeInteger(value) && value > 0
}

function duration(value: DurationDraft): Span | null {
  if (value.unit === "integer" && value.exact !== undefined && Number(value.exact) === value.amount) {
    return { amount: value.exact, unit: "integer" }
  }
  if (!whole(value.amount)) return null
  if (value.unit === "integer") return { amount: String(value.amount), unit: "integer" }
  return { amount: value.amount, unit: value.unit }
}

function policy(value: PolicyDraft): Policy | "missing" {
  if (value.mode === "none") return null
  if (value.mode === "current") return { kind: "current" }
  const older = duration(value.duration)
  return older === null ? "missing" : { kind: "older_than", older_than: older }
}

function now(value: NowDraft): Now | "missing" {
  if (value.mode === "none") return null
  if (value.mode === "current") return { kind: "current" }
  if (value.mode === "template") {
    const name = value.name.trim()
    return name === "" ? "missing" : { kind: "template", template: value.template, name }
  }
  if (value.existing === "") return "missing"
  const [schemaName, name] = JSON.parse(value.existing) as [string, string]
  return { kind: "existing", schema_name: schemaName, name }
}

/** The design the form describes, or what it still lacks. */
export function completed(draft: Draft): Completed {
  if (draft.timeColumn === "") return { missing: "Choose the time column" }
  const integer = draft.chunkInterval.unit === "integer"
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
  const merging = draft.columnstore && draft.merge && !integer
  const merge = merging ? duration(draft.mergeInterval) : null
  if (merging && merge === null) {
    return { missing: "Enter the merge interval" }
  }
  const sparseIndexes = draft.sparseIndexes.filter((item) => item.column !== "")
  if (draft.columnstore && draft.sparseMode === "columns" && sparseIndexes.length === 0) {
    return { missing: "Choose the columns of the sparse indexes" }
  }
  const retention = policy(draft.retention)
  if (retention === "missing") return { missing: "Enter the retention age" }
  const columnstorePolicy = policy(draft.columnstorePolicy)
  if (columnstorePolicy === "missing") return { missing: "Enter the columnstore policy age" }
  const clock = integer ? now(draft.now) : null
  if (clock === "missing") {
    return { missing: draft.now.mode === "template" ? "Name the integer_now function" : "Choose the integer_now function" }
  }
  return {
    design: {
      time_column: draft.timeColumn,
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
            merge_interval: merge?.unit === "integer" ? null : merge,
            sparse_indexes:
              draft.sparseMode === "columns"
                ? { mode: "columns", indexes: sparseIndexes.map((item) => ({ ...item })) }
                : { mode: draft.sparseMode },
          }
        : { enabled: false },
      retention,
      columnstore_policy: columnstorePolicy,
      reorder_index: draft.reorderIndex === "" ? null : draft.reorderIndex,
      tablespaces: [...draft.tablespaces],
      integer_now: clock,
      compaction_policy: draft.columnstore && draft.compaction,
    },
  }
}
