import type { FetchRequest, Sort } from "@/client"

export type { FetchColumn, FetchRequest, FetchResult, Sort } from "@/client"

export const PAGE_SIZES = [50, 100, 250, 500] as const
export type PageSize = (typeof PAGE_SIZES)[number]

export type Filter = NonNullable<FetchRequest["filters"]>[number]

export interface GridRow {
  id: string
  values: readonly (string | null)[]
}

export interface GridQueryState {
  page: number
  pageSize: PageSize
  filters: Filter[]
  sort: Sort[]
}

export interface StoredGridState {
  columnOrder: string[]
  columnVisibility: Record<string, boolean>
  columnSizing: Record<string, number>
  pinnedLeft: string[]
  filters: Filter[]
  sort: Sort[]
}
