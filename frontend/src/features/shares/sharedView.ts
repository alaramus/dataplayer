import type { RowsView } from "@/client"
import type { ColumnLayoutState } from "@/features/grid/columnLayout"
import { PAGE_SIZES } from "@/features/grid/types"
import type { GridQueryState, PageSize, StoredGridState } from "@/features/grid/types"

/**
 * Turning what a grid is showing into what a link carries, and back.
 *
 * Plain functions so they can be tested without mounting a grid. The page
 * number is deliberately not part of a shared view (D59): under a filter the
 * reader's page three holds different rows, so a shared offset points
 * somewhere else while the query means the same thing on both screens.
 */

export function viewOfGrid(query: GridQueryState, layout: ColumnLayoutState): RowsView {
  return {
    kind: "rows",
    filters: [...query.filters],
    sort: [...query.sort],
    page_size: query.pageSize,
    column_order: [...layout.columnOrder],
    pinned_left: [...layout.pinnedLeft],
    column_visibility: { ...layout.columnVisibility },
    column_sizing: { ...layout.columnSizing },
  }
}

/**
 * A shared view in the shape the grid already knows how to reconcile.
 *
 * The same shape a restored tab uses, so a link and a reload go through one
 * function — `reconcileGridState` — and a column that has gone since is
 * dropped once, in one place.
 */
export function storedFromView(view: RowsView): StoredGridState {
  return {
    columnOrder: [...(view.column_order ?? [])],
    columnVisibility: { ...(view.column_visibility ?? {}) },
    columnSizing: { ...(view.column_sizing ?? {}) },
    pinnedLeft: [...(view.pinned_left ?? [])],
    filters: [...(view.filters ?? [])],
    sort: [...(view.sort ?? [])],
  }
}

/** The page size of a shared view, or the default if it is not one we offer. */
export function pageSizeOf(view: RowsView, fallback: PageSize = 100): PageSize {
  const size = view.page_size
  return PAGE_SIZES.find((offered) => offered === size) ?? fallback
}

/** What a link looks like where the person reading it is. */
export function linkFor(token: string, origin: string): string {
  return `${origin}/s/${token}`
}

/**
 * What the shared query names that the relation no longer has.
 *
 * The reader is told rather than left to wonder why the sender's filter is not
 * there: reconciliation is silent by design, so the naming happens here.
 */
export function droppedByReconciliation(
  wanted: StoredGridState,
  kept: StoredGridState
): string[] {
  const keptColumns = new Set([
    ...kept.filters.map((filter) => filter.column),
    ...kept.sort.map((sort) => sort.column),
  ])
  return [
    ...new Set(
      [...wanted.filters, ...wanted.sort]
        .map((item) => item.column)
        .filter((column) => !keptColumns.has(column))
    ),
  ]
}
