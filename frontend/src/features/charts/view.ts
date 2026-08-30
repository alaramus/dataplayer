import type { FetchRequest } from "@/client"

/**
 * A short browser-local identity for one completely named bounded view.
 *
 * The full request is still stored on the panel and parsed on restore. This
 * hash is only an address for a tab and its client-only chart choice; it is
 * never used to reconstruct or authorize a read.
 */
export function chartViewKey(
  connectorId: string,
  request: FetchRequest,
  columns: readonly string[]
): string {
  const text = JSON.stringify({ connectorId, request, columns })
  let hash = 0xcbf29ce484222325n
  const prime = 0x100000001b3n
  for (let index = 0; index < text.length; index += 1) {
    hash ^= BigInt(text.charCodeAt(index))
    hash = BigInt.asUintN(64, hash * prime)
  }
  return hash.toString(36)
}
