import type { FetchColumn, FetchRequest, Sort } from "@/client"

import type { Filter, GridQueryState, PageSize } from "./types"

/**
 * The same query with every filter and sort the relation can no longer answer
 * taken out, and the names that went.
 *
 * A filter and a sort name a column by name, and both are remembered across a
 * reload, so a column renamed or dropped leaves a stored query the source will
 * refuse forever. The columns to keep are taken from an answer the source has
 * just given rather than guessed from its refusal, which is why nothing here
 * reads an error message.
 */
export function prunedToColumns(
  state: GridQueryState,
  columns: FetchColumn[]
): { state: GridQueryState; dropped: string[] } {
  const known = new Set(columns.map((column) => column.name))
  const dropped = [
    ...new Set(
      [...state.filters, ...state.sort]
        .map((item) => item.column)
        .filter((name) => !known.has(name))
    ),
  ]
  if (dropped.length === 0) return { state, dropped }
  return {
    state: {
      ...state,
      page: 0,
      filters: state.filters.filter((filter) => known.has(filter.column)),
      sort: state.sort.filter((sort) => known.has(sort.column)),
    },
    dropped,
  }
}

export function withFilters(state: GridQueryState, filters: Filter[]): GridQueryState {
  return { ...state, page: 0, filters: [...filters] }
}

export function withSort(state: GridQueryState, sort: Sort[]): GridQueryState {
  return { ...state, page: 0, sort: [...sort] }
}

export function withPageSize(state: GridQueryState, pageSize: PageSize): GridQueryState {
  return { ...state, page: 0, pageSize }
}

export function withPage(state: GridQueryState, page: number): GridQueryState {
  return { ...state, page }
}

export function buildFetchRequest(nodeId: string, state: GridQueryState): FetchRequest {
  return {
    node_id: nodeId,
    limit: state.pageSize,
    offset: state.page * state.pageSize,
    filters: [...state.filters],
    sort: [...state.sort],
  }
}
