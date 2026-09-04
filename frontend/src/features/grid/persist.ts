import { z } from "zod"
import { serverStorageKey } from "@/shared/servers/context"

import type { FetchColumn } from "@/client"

import type { PageSize, StoredGridState } from "./types"

const GRID_VERSION = 1
const DEFAULT_PAGE_SIZE: PageSize = 100
const PAGE_SIZE_KEY = "dataplayer:grid:page-size"

const scalarFilterSchema = z.strictObject({
  column: z.string(),
  op: z.enum(["contains", "eq", "gt", "gte", "lt", "lte", "ne", "starts_with"]),
  value: z.string(),
})
const inFilterSchema = z.strictObject({
  column: z.string(),
  op: z.literal("in"),
  values: z.array(z.string()).min(1),
})
const nullFilterSchema = z.strictObject({
  column: z.string(),
  op: z.enum(["is_not_null", "is_null"]),
})
const filterSchema = z.discriminatedUnion("op", [
  scalarFilterSchema,
  inFilterSchema,
  nullFilterSchema,
])
const sortSchema = z.strictObject({
  column: z.string(),
  descending: z.boolean().optional(),
})
const storedGridStateSchema = z.strictObject({
  columnOrder: z.array(z.string()),
  columnVisibility: z.record(z.string(), z.boolean()),
  columnSizing: z.record(z.string(), z.number().positive()),
  pinnedLeft: z.array(z.string()),
  filters: z.array(filterSchema),
  sort: z.array(sortSchema),
})
const envelopeSchema = z.strictObject({
  version: z.literal(GRID_VERSION),
  state: storedGridStateSchema,
})
const pageSizeSchema = z.union([z.literal(50), z.literal(100), z.literal(250), z.literal(500)])

function relationKey(connectorId: string, nodeId: string): string {
  return serverStorageKey(`dataplayer:grid:${JSON.stringify([connectorId, nodeId])}`)
}

function parseJson(raw: string): unknown | null {
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return null
  }
}

export function parseGridState(raw: string | null): StoredGridState | null {
  if (raw === null) return null

  const parsed = parseJson(raw)
  const result = envelopeSchema.safeParse(parsed)
  return result.success ? result.data.state : null
}

export function loadGridState(connectorId: string, nodeId: string): StoredGridState | null {
  return parseGridState(localStorage.getItem(relationKey(connectorId, nodeId)))
}

export function saveGridState(connectorId: string, nodeId: string, state: StoredGridState): void {
  localStorage.setItem(relationKey(connectorId, nodeId), JSON.stringify({ version: GRID_VERSION, state }))
}

export function loadPageSize(): PageSize {
  const raw = localStorage.getItem(PAGE_SIZE_KEY)
  if (raw === null) return DEFAULT_PAGE_SIZE

  const result = pageSizeSchema.safeParse(parseJson(raw))
  return result.success ? result.data : DEFAULT_PAGE_SIZE
}

export function savePageSize(pageSize: PageSize): void {
  localStorage.setItem(PAGE_SIZE_KEY, JSON.stringify(pageSize))
}

export function reconcileGridState(
  stored: StoredGridState,
  columns: readonly FetchColumn[]
): StoredGridState {
  const byName = new Map(columns.map((column) => [column.name, column]))
  const knownNames = new Set(byName.keys())

  return {
    columnOrder: reconcileOrder(stored.columnOrder, columns),
    columnVisibility: knownRecord(stored.columnVisibility, knownNames),
    columnSizing: knownRecord(stored.columnSizing, knownNames),
    pinnedLeft: knownUnique(stored.pinnedLeft, knownNames),
    filters: stored.filters.filter((filter) =>
      byName.get(filter.column)?.filter_operators?.includes(filter.op)
    ),
    sort: stored.sort.filter((sort) => byName.get(sort.column)?.sortable === true),
  }
}

function reconcileOrder(stored: readonly string[], columns: readonly FetchColumn[]): string[] {
  const known = new Set(columns.map((column) => column.name))
  const order = knownUnique(stored, known)
  const present = new Set(order)
  for (const column of columns) {
    if (!present.has(column.name)) order.push(column.name)
  }
  return order
}

function knownUnique(values: readonly string[], known: ReadonlySet<string>): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const value of values) {
    if (known.has(value) && !seen.has(value)) {
      result.push(value)
      seen.add(value)
    }
  }
  return result
}

function knownRecord<T>(values: Record<string, T>, known: ReadonlySet<string>): Record<string, T> {
  return Object.fromEntries(Object.entries(values).filter(([name]) => known.has(name)))
}
