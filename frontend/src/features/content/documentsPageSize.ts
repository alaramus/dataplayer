import { z } from "zod"

import { serverStorageKey } from "@/shared/servers/context"

/**
 * How many documents a page of the document view holds (D459).
 *
 * Its own choices rather than the grid's: a document takes the height of
 * many rows, so the grid's 500 would be a page nobody scrolls. One choice for
 * every collection, as the grid's is.
 */
export const DOCUMENT_PAGE_SIZES = [10, 20, 50, 100] as const
export type DocumentPageSize = (typeof DOCUMENT_PAGE_SIZES)[number]
export const DEFAULT_DOCUMENT_PAGE_SIZE: DocumentPageSize = 20

const KEY = "dataplayer:documents:page-size"
const schema = z.union([z.literal(10), z.literal(20), z.literal(50), z.literal(100)])

export function isDocumentPageSize(value: unknown): value is DocumentPageSize {
  return schema.safeParse(value).success
}

export function loadDocumentPageSize(): DocumentPageSize {
  const raw = localStorage.getItem(serverStorageKey(KEY))
  if (raw === null) return DEFAULT_DOCUMENT_PAGE_SIZE
  try {
    const result = schema.safeParse(JSON.parse(raw))
    return result.success ? result.data : DEFAULT_DOCUMENT_PAGE_SIZE
  } catch {
    return DEFAULT_DOCUMENT_PAGE_SIZE
  }
}

export function saveDocumentPageSize(size: DocumentPageSize): void {
  localStorage.setItem(serverStorageKey(KEY), JSON.stringify(size))
}
