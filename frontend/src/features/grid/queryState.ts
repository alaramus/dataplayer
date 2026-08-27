import type { FetchRequest, Sort } from "@/client"

import type { Filter, GridQueryState, PageSize } from "./types"

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
