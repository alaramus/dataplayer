import type { FetchResult } from "@/client"

import type { GridRow } from "./types"

export function toGridRows(result: FetchResult, offset: number): GridRow[] {
  return result.rows.map((values, index) => ({
    id: String(offset + index),
    values,
  }))
}
